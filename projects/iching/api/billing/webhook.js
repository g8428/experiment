import Stripe from 'stripe'
import { createClient } from '@supabase/supabase-js'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY)

export const config = { api: { bodyParser: false } }

async function buffer(readable) {
  const chunks = []
  for await (const chunk of readable) {
    chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk)
  }
  return Buffer.concat(chunks)
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const sig = req.headers['stripe-signature']
  const buf = await buffer(req)

  let event
  try {
    event = stripe.webhooks.constructEvent(buf, sig, process.env.STRIPE_WEBHOOK_SECRET)
  } catch (err) {
    return res.status(400).json({ error: `Webhook error: ${err.message}` })
  }

  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_SERVICE_ROLE_KEY
  )

  if (event.type === 'checkout.session.completed') {
    const s = event.data.object
    await supabase.from('subscriptions').upsert({
      user_id: s.metadata.user_id,
      stripe_customer_id: s.customer,
      stripe_subscription_id: s.subscription,
      status: 'active',
      updated_at: new Date().toISOString()
    })
  }

  if (event.type === 'customer.subscription.deleted') {
    const sub = event.data.object
    await supabase.from('subscriptions')
      .update({ status: 'cancelled', updated_at: new Date().toISOString() })
      .eq('stripe_subscription_id', sub.id)
  }

  res.json({ received: true })
}

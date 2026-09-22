import { createClient } from '@supabase/supabase-js'

export default async function handler(req, res) {
  const { code } = req.query
  if (!code) return res.redirect('/?error=no_code')

  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_ANON_KEY
  )

  const { data, error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) return res.redirect('/?error=auth_failed')

  res.setHeader('Set-Cookie', [
    `sb-access-token=${data.session.access_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
    `sb-refresh-token=${data.session.refresh_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800`
  ])

  res.redirect('/')
}

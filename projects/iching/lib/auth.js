import { createClient } from '@supabase/supabase-js'

export async function requireAuth(req, res) {
  const token = req.cookies?.['sb-access-token']
  if (!token) {
    res.status(401).json({ error: 'LOGIN_REQUIRED' })
    return null
  }

  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_ANON_KEY
  )
  const { data: { user }, error } = await supabase.auth.getUser(token)

  if (error || !user) {
    res.status(401).json({ error: 'LOGIN_REQUIRED' })
    return null
  }
  return user
}

export async function checkUsage(userId, res) {
  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_SERVICE_ROLE_KEY
  )

  // 유료 구독 확인
  const { data: sub } = await supabase
    .from('subscriptions')
    .select('status')
    .eq('user_id', userId)
    .single()

  if (sub?.status === 'active') return true

  // 이번 달 무료 사용량 확인 (월 5회)
  const startOfMonth = new Date()
  startOfMonth.setDate(1)
  startOfMonth.setHours(0, 0, 0, 0)

  const { count } = await supabase
    .from('usage_logs')
    .select('*', { count: 'exact', head: true })
    .eq('user_id', userId)
    .gte('created_at', startOfMonth.toISOString())

  if (count >= 5) {
    res.status(402).json({ error: 'FREE_LIMIT_REACHED', used: count, limit: 5 })
    return false
  }
  return true
}

export async function logUsage(userId) {
  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_SERVICE_ROLE_KEY
  )
  await supabase.from('usage_logs').insert({ user_id: userId })
}

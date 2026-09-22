-- 구독 테이블
CREATE TABLE subscriptions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  status TEXT DEFAULT 'inactive', -- 'active' | 'cancelled' | 'inactive'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- 사용량 로그 테이블
CREATE TABLE usage_logs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS (Row Level Security)
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;

-- service_role은 모두 접근 가능 (API 서버용)
CREATE POLICY "Service role full access on subscriptions"
  ON subscriptions FOR ALL TO service_role USING (true);

CREATE POLICY "Service role full access on usage_logs"
  ON usage_logs FOR ALL TO service_role USING (true);

-- 인덱스
CREATE INDEX idx_usage_logs_user_month ON usage_logs(user_id, created_at DESC);
CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);

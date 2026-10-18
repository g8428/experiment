// Vercel Serverless Function: /api/v2/saju — 생년월일시 → 사주 명식(한글). 모델 호출 없음.
import { computeSaju } from '../_lib/v2/saju.js';

export function readBirth(b = {}) {
  return {
    calendar: b.calendar === 'lunar' ? 'lunar' : 'solar',
    year: +b.year, month: +b.month, day: +b.day,
    leap: Boolean(b.leap),
    timeKnown: Boolean(b.timeKnown),
    hour: b.hour === '' || b.hour == null ? null : +b.hour,
    minute: b.minute === '' || b.minute == null ? 0 : +b.minute,
    gender: b.gender === 'F' ? 'F' : 'M',
  };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  try {
    return res.status(200).json({ saju: computeSaju(readBirth(req.body?.birth)) });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
}

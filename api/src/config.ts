import { z } from 'zod';
import dotenv from 'dotenv';

dotenv.config({ path: '../.env' });

const configSchema = z.object({
  // Server
  port: z.coerce.number().default(3000),
  host: z.string().default('0.0.0.0'),
  nodeEnv: z.enum(['development', 'production', 'test']).default('development'),

  // Python Engine
  pythonEngineUrl: z.string().default('http://localhost:8000'),

  // Redis
  redisUrl: z.string().default('redis://localhost:6379'),

  // Rate limiting
  rateLimitWindowMs: z.coerce.number().default(60000),
  rateLimitMax: z.coerce.number().default(100),

  // Auth
  apiKey: z.string().optional(),
});

function loadConfig() {
  const result = configSchema.safeParse({
    port: process.env.API_PORT,
    host: process.env.API_HOST,
    nodeEnv: process.env.NODE_ENV,
    pythonEngineUrl: process.env.PYTHON_ENGINE_URL,
    redisUrl: process.env.REDIS_URL,
    rateLimitWindowMs: process.env.RATE_LIMIT_WINDOW_MS,
    rateLimitMax: process.env.RATE_LIMIT_MAX,
    apiKey: process.env.API_KEY,
  });

  if (!result.success) {
    console.error('Configuration error:', result.error.format());
    process.exit(1);
  }

  return result.data;
}

export const config = loadConfig();
export type Config = z.infer<typeof configSchema>;

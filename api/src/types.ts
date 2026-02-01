import { z } from 'zod';

// API Response types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

// Engine State
export interface EngineState {
  running: boolean;
  dryRun: boolean;
  lastCycle: string | null;
  cyclesCompleted: number;
  totalTrades: number;
  successfulTrades: number;
  activeMarkets: number;
  tradeIntervalMinutes: number;
}

// Market types
export interface Market {
  id: string;
  question: string;
  description: string;
  outcomes: string[];
  outcomePrices: number[];
  volume: number;
  liquidity: number;
  endDate: string | null;
  category: string;
  active: boolean;
}

// Prediction types
export interface Prediction {
  marketId: string;
  direction: 'bullish' | 'bearish' | 'neutral';
  confidence: number;
  predictedProbability: number;
  currentPrice: number;
  expectedEdge: number;
  recommendedAction: string;
  timestamp: string;
}

// Trade types
export interface Trade {
  success: boolean;
  orderId: string | null;
  marketId: string;
  action: string;
  size: number;
  price: number;
  error: string | null;
  timestamp: string;
}

// Position types
export interface Position {
  marketId: string;
  outcome: number;
  size: number;
  avgPrice: number;
  currentPrice: number;
  pnl: number;
}

// Daily stats
export interface DailyStats {
  dailyPnl: number;
  totalTrades: number;
  successfulTrades: number;
  openPositions: number;
  dailyLossLimit: number;
  lossLimitRemaining: number;
}

// Request validation schemas
export const executeTradeSchema = z.object({
  marketId: z.string(),
  action: z.enum(['buy_yes', 'buy_no', 'sell_yes', 'sell_no']),
  size: z.number().positive(),
  price: z.number().min(0).max(1).optional(),
});

export const updateWeightsSchema = z.object({
  technical: z.number().min(0).max(1),
  sentiment: z.number().min(0).max(1),
  marketData: z.number().min(0).max(1),
  volatility: z.number().min(0).max(1),
});

export const engineControlSchema = z.object({
  action: z.enum(['start', 'stop', 'restart']),
  dryRun: z.boolean().optional(),
  intervalMinutes: z.number().min(1).max(60).optional(),
});

export type ExecuteTradeRequest = z.infer<typeof executeTradeSchema>;
export type UpdateWeightsRequest = z.infer<typeof updateWeightsSchema>;
export type EngineControlRequest = z.infer<typeof engineControlSchema>;

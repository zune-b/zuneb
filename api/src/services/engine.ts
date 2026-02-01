import axios, { AxiosInstance } from 'axios';
import { config } from '../config.js';
import type {
  EngineState,
  Market,
  Prediction,
  Trade,
  Position,
  DailyStats,
} from '../types.js';

/**
 * Service for communicating with the Python trading engine
 */
export class EngineService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: config.pythonEngineUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async getHealth(): Promise<{ status: string; timestamp: string }> {
    const response = await this.client.get('/health');
    return response.data;
  }

  async getEngineState(): Promise<EngineState> {
    const response = await this.client.get('/engine/state');
    return response.data;
  }

  async startEngine(dryRun: boolean = true, intervalMinutes: number = 15): Promise<void> {
    await this.client.post('/engine/start', {
      dry_run: dryRun,
      interval_minutes: intervalMinutes,
    });
  }

  async stopEngine(): Promise<void> {
    await this.client.post('/engine/stop');
  }

  async runCycle(): Promise<{
    cycle: number;
    marketsAnalyzed: number;
    predictions: number;
    tradesExecuted: number;
    successfulTrades: number;
  }> {
    const response = await this.client.post('/engine/run-cycle');
    return response.data;
  }

  async getMarkets(): Promise<Market[]> {
    const response = await this.client.get('/markets');
    return response.data;
  }

  async getMarket(marketId: string): Promise<Market> {
    const response = await this.client.get(`/markets/${marketId}`);
    return response.data;
  }

  async getPredictions(): Promise<Prediction[]> {
    const response = await this.client.get('/predictions');
    return response.data;
  }

  async getPrediction(marketId: string): Promise<Prediction> {
    const response = await this.client.get(`/predictions/${marketId}`);
    return response.data;
  }

  async getTrades(): Promise<Trade[]> {
    const response = await this.client.get('/trades');
    return response.data;
  }

  async executeTrade(
    marketId: string,
    action: string,
    size: number,
    price?: number
  ): Promise<Trade> {
    const response = await this.client.post('/trades/execute', {
      market_id: marketId,
      action,
      size,
      price,
    });
    return response.data;
  }

  async getPositions(): Promise<Position[]> {
    const response = await this.client.get('/positions');
    return response.data;
  }

  async closePosition(marketId: string): Promise<Trade> {
    const response = await this.client.post(`/positions/${marketId}/close`);
    return response.data;
  }

  async closeAllPositions(): Promise<Trade[]> {
    const response = await this.client.post('/positions/close-all');
    return response.data;
  }

  async getDailyStats(): Promise<DailyStats> {
    const response = await this.client.get('/stats/daily');
    return response.data;
  }

  async getSignalWeights(): Promise<Record<string, number>> {
    const response = await this.client.get('/config/weights');
    return response.data;
  }

  async updateSignalWeights(weights: Record<string, number>): Promise<void> {
    await this.client.put('/config/weights', weights);
  }
}

// Singleton instance
export const engineService = new EngineService();

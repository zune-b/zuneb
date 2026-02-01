import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import { executeTradeSchema } from '../types.js';
import type { ApiResponse, Trade } from '../types.js';

const router = Router();

// Get trade history
router.get('/', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const trades = await engineService.getTrades();

    const response: ApiResponse<Trade[]> = {
      success: true,
      data: trades,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Execute a manual trade
router.post('/execute', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const validation = executeTradeSchema.safeParse(req.body);

    if (!validation.success) {
      res.status(400).json({
        success: false,
        error: validation.error.message,
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const { marketId, action, size, price } = validation.data;
    const trade = await engineService.executeTrade(marketId, action, size, price);

    const response: ApiResponse<Trade> = {
      success: true,
      data: trade,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

export default router;

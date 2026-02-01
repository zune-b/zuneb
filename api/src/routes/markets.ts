import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import type { ApiResponse, Market } from '../types.js';

const router = Router();

// Get all markets
router.get('/', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const markets = await engineService.getMarkets();

    const response: ApiResponse<Market[]> = {
      success: true,
      data: markets,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Get specific market
router.get('/:marketId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { marketId } = req.params;
    const market = await engineService.getMarket(marketId);

    const response: ApiResponse<Market> = {
      success: true,
      data: market,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

export default router;

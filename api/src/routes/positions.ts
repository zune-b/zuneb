import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import type { ApiResponse, Position, Trade } from '../types.js';

const router = Router();

// Get all positions
router.get('/', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const positions = await engineService.getPositions();

    const response: ApiResponse<Position[]> = {
      success: true,
      data: positions,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Close specific position
router.post('/:marketId/close', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { marketId } = req.params;
    const trade = await engineService.closePosition(marketId);

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

// Close all positions
router.post('/close-all', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const trades = await engineService.closeAllPositions();

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

export default router;

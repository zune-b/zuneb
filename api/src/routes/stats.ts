import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import type { ApiResponse, DailyStats } from '../types.js';

const router = Router();

// Get daily stats
router.get('/daily', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const stats = await engineService.getDailyStats();

    const response: ApiResponse<DailyStats> = {
      success: true,
      data: stats,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

export default router;

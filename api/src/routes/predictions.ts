import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import type { ApiResponse, Prediction } from '../types.js';

const router = Router();

// Get all predictions
router.get('/', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const predictions = await engineService.getPredictions();

    const response: ApiResponse<Prediction[]> = {
      success: true,
      data: predictions,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Get prediction for specific market
router.get('/:marketId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { marketId } = req.params;
    const prediction = await engineService.getPrediction(marketId);

    const response: ApiResponse<Prediction> = {
      success: true,
      data: prediction,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

export default router;

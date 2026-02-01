import { Router, Request, Response, NextFunction } from 'express';
import { engineService } from '../services/engine.js';
import { engineControlSchema, updateWeightsSchema } from '../types.js';
import type { ApiResponse, EngineState } from '../types.js';

const router = Router();

// Get engine state
router.get('/state', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const state = await engineService.getEngineState();

    const response: ApiResponse<EngineState> = {
      success: true,
      data: state,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Control engine (start/stop/restart)
router.post('/control', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const validation = engineControlSchema.safeParse(req.body);

    if (!validation.success) {
      res.status(400).json({
        success: false,
        error: validation.error.message,
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const { action, dryRun = true, intervalMinutes = 15 } = validation.data;

    switch (action) {
      case 'start':
        await engineService.startEngine(dryRun, intervalMinutes);
        break;
      case 'stop':
        await engineService.stopEngine();
        break;
      case 'restart':
        await engineService.stopEngine();
        await engineService.startEngine(dryRun, intervalMinutes);
        break;
    }

    const response: ApiResponse<{ action: string; success: boolean }> = {
      success: true,
      data: { action, success: true },
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Run single cycle
router.post('/run-cycle', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await engineService.runCycle();

    const response: ApiResponse<typeof result> = {
      success: true,
      data: result,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Get signal weights
router.get('/weights', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const weights = await engineService.getSignalWeights();

    const response: ApiResponse<Record<string, number>> = {
      success: true,
      data: weights,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

// Update signal weights
router.put('/weights', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const validation = updateWeightsSchema.safeParse(req.body);

    if (!validation.success) {
      res.status(400).json({
        success: false,
        error: validation.error.message,
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const weights = validation.data;

    // Validate weights sum to 1
    const sum = Object.values(weights).reduce((a, b) => a + b, 0);
    if (Math.abs(sum - 1) > 0.001) {
      res.status(400).json({
        success: false,
        error: 'Weights must sum to 1.0',
        timestamp: new Date().toISOString(),
      });
      return;
    }

    await engineService.updateSignalWeights(weights);

    const response: ApiResponse<Record<string, number>> = {
      success: true,
      data: weights,
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    next(error);
  }
});

export default router;

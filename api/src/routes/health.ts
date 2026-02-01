import { Router, Request, Response } from 'express';
import { engineService } from '../services/engine.js';
import type { ApiResponse } from '../types.js';

const router = Router();

router.get('/', async (_req: Request, res: Response) => {
  const response: ApiResponse<{ status: string; components: Record<string, string> }> = {
    success: true,
    data: {
      status: 'healthy',
      components: {
        api: 'healthy',
        engine: 'unknown',
      },
    },
    timestamp: new Date().toISOString(),
  };

  try {
    await engineService.getHealth();
    response.data!.components.engine = 'healthy';
  } catch {
    response.data!.components.engine = 'unhealthy';
  }

  res.json(response);
});

export default router;

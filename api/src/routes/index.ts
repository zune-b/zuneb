import { Router } from 'express';
import healthRoutes from './health.js';
import engineRoutes from './engine.js';
import marketsRoutes from './markets.js';
import predictionsRoutes from './predictions.js';
import tradesRoutes from './trades.js';
import positionsRoutes from './positions.js';
import statsRoutes from './stats.js';

const router = Router();

router.use('/health', healthRoutes);
router.use('/engine', engineRoutes);
router.use('/markets', marketsRoutes);
router.use('/predictions', predictionsRoutes);
router.use('/trades', tradesRoutes);
router.use('/positions', positionsRoutes);
router.use('/stats', statsRoutes);

export default router;

import { Router, Request, Response } from 'express';
import { verifyToken } from './auth';

export const usersRouter = Router();

const store: Record<number, { id: number; email: string; name: string; role: string }> = {
  1: { id: 1, email: 'user@test.com', name: 'Alice', role: 'user' },
  2: { id: 2, email: 'admin@test.com', name: 'Bob', role: 'admin' },
};

usersRouter.get('/', verifyToken, (_req: Request, res: Response) => {
  res.json({ items: Object.values(store), total: Object.keys(store).length });
});

usersRouter.get('/:id', verifyToken, (req: Request, res: Response) => {
  const user = store[Number(req.params.id)];
  if (!user) return res.status(404).json({ error: 'Not found' });
  res.json(user);
});

usersRouter.put('/:id', verifyToken, (req: Request, res: Response) => {
  const userId = Number(req.params.id);
  const user = store[userId];
  if (!user) return res.status(404).json({ error: 'Not found' });
  const requester = (req as any).user;
  if (requester.sub !== userId && requester.role !== 'admin') {
    return res.status(403).json({ error: 'Forbidden' });
  }
  const { name, email } = req.body;
  if (name) user.name = name;
  if (email) user.email = email;
  res.json(user);
});

import { Router, Request, Response } from 'express';
import { getUserById, getAllUsers, createUser, updateUser, deleteUser } from '../services/userService';

export const usersRouter = Router();

usersRouter.get('/', async (req: Request, res: Response) => {
  const page = parseInt(req.query.page as string) || 1;
  const limit = parseInt(req.query.limit as string) || 10;
  const users = await getAllUsers(page, limit);
  res.json({ items: users.data, total: users.total, page, limit });
});

usersRouter.get('/me', async (req: Request, res: Response) => {
  const userId = (req as any).userId;
  const user = await getUserById(userId);
  if (!user) return res.status(404).json({ error: 'User not found' });
  const { passwordHash, ...safeUser } = user;
  res.json(safeUser);
});

usersRouter.get('/:id', async (req: Request, res: Response) => {
  const user = await getUserById(req.params.id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  const { passwordHash, ...safeUser } = user;
  res.json(safeUser);
});

usersRouter.post('/', async (req: Request, res: Response) => {
  const { email, password, name } = req.body;
  const user = await createUser({ email, password, name });
  res.status(201).json(user);
});

usersRouter.put('/:id', async (req: Request, res: Response) => {
  const user = await updateUser(req.params.id, req.body);
  res.json(user);
});

usersRouter.delete('/:id', async (req: Request, res: Response) => {
  await deleteUser(req.params.id);
  res.status(204).send();
});

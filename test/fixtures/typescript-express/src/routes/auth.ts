import { Router, Request, Response } from 'express';
import { loginUser, refreshToken } from '../services/userService';

export const authRouter = Router();

authRouter.post('/login', async (req: Request, res: Response) => {
  const { email, password } = req.body;
  try {
    const result = await loginUser(email, password);
    res.json({ token: result.token, refreshToken: result.refreshToken });
  } catch (err: any) {
    res.status(401).json({ error: 'Invalid credentials' });
  }
});

authRouter.post('/refresh', async (req: Request, res: Response) => {
  const { refreshToken: token } = req.body;
  try {
    const result = await refreshToken(token);
    res.json({ token: result.token });
  } catch {
    res.status(401).json({ error: 'Invalid refresh token' });
  }
});

authRouter.post('/logout', (req: Request, res: Response) => {
  res.json({ success: true });
});

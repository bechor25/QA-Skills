import { Router, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';

export const authRouter = Router();

const SECRET = process.env.JWT_SECRET || 'dev-secret';

const users: Record<string, { id: number; email: string; passwordHash: string; role: string }> = {
  'user@test.com': {
    id: 1,
    email: 'user@test.com',
    passwordHash: bcrypt.hashSync('TestPass1!', 10),
    role: 'user',
  },
  'admin@test.com': {
    id: 2,
    email: 'admin@test.com',
    passwordHash: bcrypt.hashSync('AdminPass1!', 10),
    role: 'admin',
  },
};

export function verifyToken(req: Request, res: Response, next: Function) {
  const auth = req.headers.authorization;
  if (!auth || !auth.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'No token' });
  }
  try {
    const payload = jwt.verify(auth.slice(7), SECRET) as object;
    (req as any).user = payload;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}

authRouter.post('/login', (req: Request, res: Response) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'email and password required' });
  }
  const user = users[email];
  if (!user || !bcrypt.compareSync(password, user.passwordHash)) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }
  const token = jwt.sign({ sub: user.id, role: user.role }, SECRET, { expiresIn: '1h' });
  res.json({ token });
});

authRouter.get('/me', verifyToken, (req: Request, res: Response) => {
  res.json((req as any).user);
});

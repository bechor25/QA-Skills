import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { db } from '../models/db';
import { User } from '../models/User';

const JWT_SECRET = process.env.JWT_SECRET || 'change-me-in-production';
const SALT_ROUNDS = 12;

export async function loginUser(email: string, password: string) {
  if (!email || !password) throw new Error('Email and password required');

  const user = await db.query<User>('SELECT * FROM users WHERE email = $1', [email]);
  if (!user.rows[0]) throw new Error('Invalid credentials');

  const valid = await bcrypt.compare(password, user.rows[0].passwordHash);
  if (!valid) throw new Error('Invalid credentials');

  const token = jwt.sign({ sub: user.rows[0].id, role: user.rows[0].role }, JWT_SECRET, { expiresIn: '1h' });
  const refreshToken = jwt.sign({ sub: user.rows[0].id }, JWT_SECRET, { expiresIn: '7d' });

  return { token, refreshToken };
}

export async function refreshToken(token: string) {
  const decoded = jwt.verify(token, JWT_SECRET) as { sub: string };
  const newToken = jwt.sign({ sub: decoded.sub }, JWT_SECRET, { expiresIn: '1h' });
  return { token: newToken };
}

export async function getUserById(id: string) {
  const result = await db.query<User>('SELECT * FROM users WHERE id = $1', [id]);
  return result.rows[0] || null;
}

export async function getAllUsers(page: number, limit: number) {
  const offset = (page - 1) * limit;
  const result = await db.query<User>('SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2', [limit, offset]);
  const count = await db.query<{ count: string }>('SELECT COUNT(*) FROM users');
  return { data: result.rows, total: parseInt(count.rows[0].count) };
}

export async function createUser(input: { email: string; password: string; name: string }) {
  const existing = await db.query('SELECT id FROM users WHERE email = $1', [input.email]);
  if (existing.rows[0]) throw new Error('Email already registered');

  const passwordHash = await bcrypt.hash(input.password, SALT_ROUNDS);
  const result = await db.query<User>(
    'INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3) RETURNING id, email, name, role, created_at',
    [input.email, passwordHash, input.name]
  );
  return result.rows[0];
}

export async function updateUser(id: string, updates: Partial<User>) {
  const { passwordHash, role, ...safeUpdates } = updates as any;
  const result = await db.query<User>(
    'UPDATE users SET name = $1 WHERE id = $2 RETURNING id, email, name, role',
    [safeUpdates.name, id]
  );
  return result.rows[0];
}

export async function deleteUser(id: string) {
  await db.query('DELETE FROM users WHERE id = $1', [id]);
}

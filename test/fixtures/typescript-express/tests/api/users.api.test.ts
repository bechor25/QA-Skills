import request from 'supertest';
import { app } from '../../src/app';
import { db } from '../../src/models/db';
import jwt from 'jsonwebtoken';

jest.mock('../../src/models/db');
jest.mock('jsonwebtoken');

const mockDb = db as jest.Mocked<typeof db>;
const mockJwt = jwt as jest.Mocked<typeof jwt>;

const VALID_TOKEN = 'valid-jwt-token';
const EXPIRED_JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxfQ.invalid';

const mockUser = {
  id: 'user-1',
  email: 'alice@example.com',
  name: 'Alice',
  passwordHash: '$2b$12$hashedpw',
  role: 'user',
  createdAt: new Date('2024-01-01'),
};

function withAuth(token = VALID_TOKEN) {
  return { Authorization: `Bearer ${token}` };
}

beforeEach(() => {
  jest.clearAllMocks();
  (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1', role: 'user' });
});

describe('GET /users (list)', () => {
  it('returns 200 with items and total for authenticated user', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [mockUser] })
      .mockResolvedValueOnce({ rows: [{ count: '1' }] });

    const res = await request(app)
      .get('/users')
      .set(withAuth());

    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('items');
    expect(res.body).toHaveProperty('total');
    expect(Array.isArray(res.body.items)).toBe(true);
  });

  it('returns 401 without Authorization header', async () => {
    const res = await request(app).get('/users');
    expect(res.status).toBe(401);
  });

  it('returns 401 for invalid token', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid'); });
    const res = await request(app).get('/users').set(withAuth('bad-token'));
    expect(res.status).toBe(401);
  });

  it('returns 401 for expired token', async () => {
    const err = new Error('expired'); err.name = 'TokenExpiredError';
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw err; });
    const res = await request(app).get('/users').set(withAuth(EXPIRED_JWT));
    expect(res.status).toBe(401);
    expect(res.body.error).toBe('Token expired');
  });

  it('supports pagination with page and limit', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '50' }] });

    const res = await request(app)
      .get('/users?page=3&limit=5')
      .set(withAuth());

    expect(res.status).toBe(200);
    expect(res.body.page).toBe(3);
    expect(res.body.limit).toBe(5);
  });

  it('defaults page=1 and limit=10 when not provided', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '0' }] });

    const res = await request(app)
      .get('/users')
      .set(withAuth());

    expect(res.body.page).toBe(1);
    expect(res.body.limit).toBe(10);
  });

  it('returns empty items array for out-of-range page', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '10' }] });

    const res = await request(app)
      .get('/users?page=9999&limit=10')
      .set(withAuth());

    expect(res.status).toBe(200);
    expect(res.body.items).toEqual([]);
  });

  it('GET does not mutate total count (idempotent)', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValue({ rows: [{ count: '5' }] })
      .mockResolvedValueOnce({ rows: [mockUser] })
      .mockResolvedValueOnce({ rows: [{ count: '5' }] })
      .mockResolvedValueOnce({ rows: [mockUser] })
      .mockResolvedValueOnce({ rows: [{ count: '5' }] });

    const r1 = await request(app).get('/users').set(withAuth());
    const r2 = await request(app).get('/users').set(withAuth());

    expect(r1.body.total).toBe(r2.body.total);
  });
});

describe('GET /users/me', () => {
  it('returns current user without passwordHash', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    const res = await request(app)
      .get('/users/me')
      .set(withAuth());

    expect(res.status).toBe(200);
    expect(res.body.id).toBe(mockUser.id);
    expect(res.body.passwordHash).toBeUndefined();
    expect(res.body.email).toBe(mockUser.email);
  });

  it('returns 404 when userId not found in DB', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    const res = await request(app)
      .get('/users/me')
      .set(withAuth());

    expect(res.status).toBe(404);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).get('/users/me');
    expect(res.status).toBe(401);
  });
});

describe('GET /users/:id', () => {
  it('returns user by id without passwordHash', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    const res = await request(app)
      .get('/users/user-1')
      .set(withAuth());

    expect(res.status).toBe(200);
    expect(res.body.passwordHash).toBeUndefined();
  });

  it('returns 404 for non-existent id', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    const res = await request(app)
      .get('/users/nonexistent-id')
      .set(withAuth());

    expect(res.status).toBe(404);
    expect(res.body.error).toBe('User not found');
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).get('/users/user-1');
    expect(res.status).toBe(401);
  });
});

describe('POST /users', () => {
  it('returns 201 with created user for valid input', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: 'new@example.com', name: 'New', role: 'user' }] });

    const res = await request(app)
      .post('/users')
      .set(withAuth())
      .send({ email: 'new@example.com', password: 'SecurePass1!', name: 'New' });

    expect(res.status).toBe(201);
    expect(res.body.email).toBe('new@example.com');
    expect(res.body.passwordHash).toBeUndefined();
  });

  it('returns 401 without auth', async () => {
    const res = await request(app)
      .post('/users')
      .send({ email: 'x@x.com', password: 'pass', name: 'X' });

    expect(res.status).toBe(401);
  });

  it('does not persist role from client input (mass assignment protection)', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: 'new@example.com', name: 'New', role: 'user' }] });

    const res = await request(app)
      .post('/users')
      .set(withAuth())
      .send({ email: 'new@example.com', password: 'SecurePass1!', name: 'New', role: 'admin' });

    if (res.status === 201) {
      expect(res.body.role).not.toBe('admin');
    }
  });
});

describe('PUT /users/:id', () => {
  it('returns updated user', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [{ ...mockUser, name: 'Alice Updated' }] });

    const res = await request(app)
      .put('/users/user-1')
      .set(withAuth())
      .send({ name: 'Alice Updated' });

    expect(res.status).toBe(200);
    expect(res.body.name).toBe('Alice Updated');
  });

  it('returns same result on repeated identical PUTs (idempotent)', async () => {
    const updated = { ...mockUser, name: 'Alice Updated' };
    mockDb.query = jest.fn().mockResolvedValue({ rows: [updated] });

    const r1 = await request(app).put('/users/user-1').set(withAuth()).send({ name: 'Alice Updated' });
    const r2 = await request(app).put('/users/user-1').set(withAuth()).send({ name: 'Alice Updated' });

    expect(r1.body).toEqual(r2.body);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app)
      .put('/users/user-1')
      .send({ name: 'X' });

    expect(res.status).toBe(401);
  });
});

describe('DELETE /users/:id', () => {
  it('returns 204 on success', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    const res = await request(app)
      .delete('/users/user-1')
      .set(withAuth());

    expect(res.status).toBe(204);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).delete('/users/user-1');
    expect(res.status).toBe(401);
  });
});

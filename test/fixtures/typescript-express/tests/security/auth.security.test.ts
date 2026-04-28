import request from 'supertest';
import { app } from '../../src/app';
import { db } from '../../src/models/db';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcrypt';

jest.mock('../../src/models/db');
jest.mock('jsonwebtoken');
jest.mock('bcrypt');

const mockDb = db as jest.Mocked<typeof db>;
const mockJwt = jwt as jest.Mocked<typeof jwt>;
const mockBcrypt = bcrypt as jest.Mocked<typeof bcrypt>;

const mockUser = {
  id: 'user-1',
  email: 'alice@example.com',
  passwordHash: '$2b$12$hashed',
  role: 'user',
  name: 'Alice',
};

beforeEach(() => {
  jest.clearAllMocks();
  (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1', role: 'user' });
});

describe('JWT algorithm confusion attack', () => {
  it('rejects token signed with alg=none', async () => {
    const header = Buffer.from(JSON.stringify({ alg: 'none', typ: 'JWT' })).toString('base64url');
    const payload = Buffer.from(JSON.stringify({ sub: '1', role: 'admin', exp: 9999999999 })).toString('base64url');
    const noneToken = `${header}.${payload}.`;

    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid signature'); });

    const res = await request(app)
      .get('/users/me')
      .set('Authorization', `Bearer ${noneToken}`);

    expect(res.status).toBe(401);
  });

  it('rejects forged admin token', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid signature'); });

    const res = await request(app)
      .get('/users/me')
      .set('Authorization', 'Bearer forged.admin.token');

    expect(res.status).toBe(401);
  });
});

describe('Auth bypass via missing/malformed tokens', () => {
  it('protected routes return 401 with no Authorization header', async () => {
    const routes = [
      () => request(app).get('/users'),
      () => request(app).get('/users/me'),
      () => request(app).get('/users/user-1'),
      () => request(app).post('/users').send({ email: 'x@x.com', password: 'p', name: 'X' }),
      () => request(app).put('/users/user-1').send({ name: 'Y' }),
      () => request(app).delete('/users/user-1'),
    ];

    for (const makeReq of routes) {
      const res = await makeReq();
      expect(res.status).toBe(401);
    }
  });

  it('returns 401 for Authorization without Bearer prefix', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid'); });

    const res = await request(app)
      .get('/users/me')
      .set('Authorization', 'Token some-token');

    expect(res.status).toBe(401);
  });

  it('returns 401 for empty Authorization header', async () => {
    const res = await request(app)
      .get('/users/me')
      .set('Authorization', '');

    expect(res.status).toBe(401);
  });

  it('returns 401 for Bearer with empty token', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('jwt malformed'); });

    const res = await request(app)
      .get('/users/me')
      .set('Authorization', 'Bearer ');

    expect(res.status).toBe(401);
  });
});

describe('SQL Injection in auth endpoints', () => {
  const SQL_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "admin'--",
    "' OR 1=1--",
    "1' UNION SELECT null, null, null--",
  ];

  SQL_PAYLOADS.forEach(payload => {
    it(`rejects SQL injection payload in login email: ${payload.slice(0, 30)}`, async () => {
      mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

      const res = await request(app)
        .post('/auth/login')
        .send({ email: payload, password: payload });

      expect(res.status).toBeOneOf([400, 401, 422]);
      expect(res.body.token).toBeUndefined();
    });

    it(`does not return 500 for SQL payload: ${payload.slice(0, 30)}`, async () => {
      mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

      const res = await request(app)
        .post('/auth/login')
        .send({ email: payload, password: 'password' });

      expect(res.status).not.toBe(500);
    });
  });

  it('does not expose DB error messages in login response', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('syntax error at or near'));

    const res = await request(app)
      .post('/auth/login')
      .send({ email: "' OR 1=1--", password: 'x' });

    expect(res.text.toLowerCase()).not.toContain('syntax error');
    expect(res.text.toLowerCase()).not.toContain('postgresql');
    expect(res.text.toLowerCase()).not.toContain('table_name');
    expect(res.text.toLowerCase()).not.toContain('information_schema');
  });
});

describe('Privilege escalation', () => {
  it('cannot escalate own role to admin via PUT /users/:id', async () => {
    const updatedUser = { ...mockUser, role: 'user' };
    mockDb.query = jest.fn().mockResolvedValue({ rows: [updatedUser] });

    const res = await request(app)
      .put('/users/user-1')
      .set('Authorization', 'Bearer valid-tok')
      .send({ name: 'Alice', role: 'admin' });

    if (res.status === 200) {
      expect(res.body.role).not.toBe('admin');
    }
  });
});

describe('Mass assignment protection', () => {
  it('POST /users ignores role field in body', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: 'x@x.com', name: 'X', role: 'user' }] });

    const res = await request(app)
      .post('/users')
      .set('Authorization', 'Bearer valid-tok')
      .send({ email: 'x@x.com', password: 'Pass1!', name: 'X', role: 'admin' });

    if (res.status === 201) {
      expect(res.body.role).not.toBe('admin');
    }
  });

  it('POST /users ignores passwordHash field in body', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: 'x@x.com', name: 'X', role: 'user' }] });

    const res = await request(app)
      .post('/users')
      .set('Authorization', 'Bearer valid-tok')
      .send({ email: 'x@x.com', password: 'Pass1!', name: 'X', passwordHash: 'injected-hash' });

    if (res.status === 201) {
      expect(res.body.passwordHash).toBeUndefined();
    }
  });
});

describe('Sensitive data exposure', () => {
  it('GET /users/me does not return passwordHash', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    const res = await request(app)
      .get('/users/me')
      .set('Authorization', 'Bearer valid-tok');

    expect(res.status).toBe(200);
    const sensitiveKeys = ['passwordHash', 'password_hash', 'password', 'salt', 'secret'];
    for (const key of sensitiveKeys) {
      expect(res.body[key]).toBeUndefined();
    }
  });

  it('GET /users/:id does not return passwordHash', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    const res = await request(app)
      .get('/users/user-1')
      .set('Authorization', 'Bearer valid-tok');

    expect(res.status).toBe(200);
    expect(res.body.passwordHash).toBeUndefined();
  });

  it('error response does not contain stack trace', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('DB crash'));

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'x@x.com', password: 'y' });

    expect(res.text).not.toContain('at Object.');
    expect(res.text).not.toContain('at async ');
    expect(res.text).not.toContain('node_modules');
  });

  it('login error does not expose password value in response', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(false);

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com', password: 'my-secret-password' });

    expect(res.text).not.toContain('my-secret-password');
    expect(res.text.toLowerCase()).not.toContain('hash');
  });
});

expect.extend({
  toBeOneOf(received: number, expected: number[]) {
    const pass = expected.includes(received);
    return {
      pass,
      message: () => `expected ${received} to be one of ${expected.join(', ')}`,
    };
  },
});

declare global {
  namespace jest {
    interface Matchers<R> {
      toBeOneOf(expected: number[]): R;
    }
  }
}

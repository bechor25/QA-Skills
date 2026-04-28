import request from 'supertest';
import { app } from '../../src/app';
import { db } from '../../src/models/db';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

jest.mock('../../src/models/db');
jest.mock('bcrypt');
jest.mock('jsonwebtoken');

const mockDb = db as jest.Mocked<typeof db>;
const mockBcrypt = bcrypt as jest.Mocked<typeof bcrypt>;
const mockJwt = jwt as jest.Mocked<typeof jwt>;

const EXPIRED_JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxfQ.invalid';

const mockUser = {
  id: 'user-1',
  email: 'alice@example.com',
  passwordHash: '$2b$12$hashedpw',
  role: 'user',
  name: 'Alice',
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('POST /auth/login', () => {
  it('returns 200 with token and refreshToken for valid credentials', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(true);
    (mockJwt.sign as jest.Mock)
      .mockReturnValueOnce('access-tok')
      .mockReturnValueOnce('refresh-tok');

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com', password: 'ValidPass1!' });

    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
    expect(res.body.refreshToken).toBeDefined();
    expect(typeof res.body.token).toBe('string');
  });

  it('returns 401 for wrong password', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(false);

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com', password: 'wrongpassword' });

    expect(res.status).toBe(401);
    expect(res.body.error).toBe('Invalid credentials');
    expect(res.body.token).toBeUndefined();
  });

  it('returns 401 for non-existent email', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'nobody@example.com', password: 'password' });

    expect(res.status).toBe(401);
    expect(res.body.token).toBeUndefined();
  });

  it('returns 401 for missing email', async () => {
    const res = await request(app)
      .post('/auth/login')
      .send({ password: 'password' });

    expect(res.status).toBe(401);
    expect(res.body.token).toBeUndefined();
  });

  it('returns 401 for missing password', async () => {
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com' });

    expect(res.status).toBe(401);
    expect(res.body.token).toBeUndefined();
  });

  it('returns 401 for empty body', async () => {
    const res = await request(app)
      .post('/auth/login')
      .send({});

    expect(res.status).toBe(401);
  });

  it('does not expose password or hash in error response', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(false);

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com', password: 'wrong' });

    expect(res.text.toLowerCase()).not.toContain('hash');
    expect(res.text.toLowerCase()).not.toContain('password');
    expect(res.text).not.toContain('$2b$');
  });

  it('does not expose stack trace on error', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('DB crash'));

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'alice@example.com', password: 'pass' });

    expect(res.text).not.toContain('at Object.');
    expect(res.text).not.toContain('at async');
  });

  it('returns consistent error shape', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'x@x.com', password: 'y' });

    expect(res.body).toHaveProperty('error');
  });
});

describe('POST /auth/refresh', () => {
  it('returns 200 with new token for valid refresh token', async () => {
    (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1' });
    (mockJwt.sign as jest.Mock).mockReturnValue('new-access-tok');

    const res = await request(app)
      .post('/auth/refresh')
      .send({ refreshToken: 'valid-refresh-token' });

    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
  });

  it('returns 401 for invalid refresh token', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid'); });

    const res = await request(app)
      .post('/auth/refresh')
      .send({ refreshToken: 'bad-token' });

    expect(res.status).toBe(401);
    expect(res.body.error).toBe('Invalid refresh token');
  });

  it('returns 401 for expired refresh token', async () => {
    const err = new Error('expired');
    err.name = 'TokenExpiredError';
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw err; });

    const res = await request(app)
      .post('/auth/refresh')
      .send({ refreshToken: EXPIRED_JWT });

    expect(res.status).toBe(401);
  });

  it('returns 401 for missing refreshToken field', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid'); });

    const res = await request(app)
      .post('/auth/refresh')
      .send({});

    expect(res.status).toBe(401);
  });
});

describe('POST /auth/logout', () => {
  it('returns 200 with success: true', async () => {
    const res = await request(app)
      .post('/auth/logout')
      .send();

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
  });

  it('succeeds without Authorization header (stateless logout)', async () => {
    const res = await request(app)
      .post('/auth/logout');

    expect(res.status).toBe(200);
  });
});

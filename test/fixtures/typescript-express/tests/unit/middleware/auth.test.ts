import { authMiddleware, requireRole } from '../../../src/middleware/auth';
import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

jest.mock('jsonwebtoken');
const mockJwt = jwt as jest.Mocked<typeof jwt>;

function makeReq(authHeader?: string): Request {
  return {
    headers: { authorization: authHeader },
  } as unknown as Request;
}

function makeRes(): { res: Response; status: jest.Mock; json: jest.Mock } {
  const json = jest.fn();
  const status = jest.fn().mockReturnValue({ json });
  const res = { status } as unknown as Response;
  return { res, status, json };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('authMiddleware', () => {
  it('calls next() and sets userId/userRole for valid token', () => {
    (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1', role: 'user' });
    const req = makeReq('Bearer valid-token');
    const { res } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect((req as any).userId).toBe('user-1');
    expect((req as any).userRole).toBe('user');
  });

  it('returns 401 when Authorization header missing', () => {
    const req = makeReq(undefined);
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(status).toHaveBeenCalledWith(401);
    expect(json).toHaveBeenCalledWith({ error: 'Missing or invalid Authorization header' });
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when Authorization header has wrong format (no Bearer)', () => {
    const req = makeReq('Token abc123');
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 for expired token with specific message', () => {
    const expiredError = new Error('jwt expired');
    expiredError.name = 'TokenExpiredError';
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw expiredError; });

    const req = makeReq('Bearer expired-token');
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(status).toHaveBeenCalledWith(401);
    expect(json).toHaveBeenCalledWith({ error: 'Token expired' });
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 for invalid token signature', () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid signature'); });

    const req = makeReq('Bearer bad-token');
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(status).toHaveBeenCalledWith(401);
    expect(json).toHaveBeenCalledWith({ error: 'Invalid token' });
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 for empty Bearer token', () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('jwt malformed'); });

    const req = makeReq('Bearer ');
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });

  it('does not expose internal error message for unknown jwt errors', () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('some internal error'); });

    const req = makeReq('Bearer bad');
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    authMiddleware(req, res, next);

    expect(json).toHaveBeenCalledWith({ error: 'Invalid token' });
  });

  it('strips Bearer prefix before passing to jwt.verify', () => {
    (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'u1', role: 'user' });

    const req = makeReq('Bearer the-actual-token');
    const { res } = makeRes();

    authMiddleware(req, res, jest.fn());

    expect(mockJwt.verify).toHaveBeenCalledWith('the-actual-token', expect.any(String));
  });
});

describe('requireRole', () => {
  it('calls next() when role matches', () => {
    const req = { userRole: 'admin' } as any;
    const { res } = makeRes();
    const next = jest.fn() as NextFunction;

    requireRole('admin')(req, res, next);

    expect(next).toHaveBeenCalled();
  });

  it('returns 403 when role does not match', () => {
    const req = { userRole: 'user' } as any;
    const { res, status, json } = makeRes();
    const next = jest.fn() as NextFunction;

    requireRole('admin')(req, res, next);

    expect(status).toHaveBeenCalledWith(403);
    expect(json).toHaveBeenCalledWith({ error: 'Insufficient permissions' });
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 403 when userRole is undefined', () => {
    const req = {} as any;
    const { res, status } = makeRes();
    const next = jest.fn() as NextFunction;

    requireRole('admin')(req, res, next);

    expect(status).toHaveBeenCalledWith(403);
    expect(next).not.toHaveBeenCalled();
  });

  it('is case-sensitive for role comparison', () => {
    const req = { userRole: 'Admin' } as any;
    const { res, status } = makeRes();
    const next = jest.fn() as NextFunction;

    requireRole('admin')(req, res, next);

    expect(status).toHaveBeenCalledWith(403);
    expect(next).not.toHaveBeenCalled();
  });
});

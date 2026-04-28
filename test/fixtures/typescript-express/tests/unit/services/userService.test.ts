import { loginUser, refreshToken, getUserById, getAllUsers, createUser, updateUser, deleteUser } from '../../../src/services/userService';
import { db } from '../../../src/models/db';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

jest.mock('../../../src/models/db');
jest.mock('bcrypt');
jest.mock('jsonwebtoken');

const mockDb = db as jest.Mocked<typeof db>;
const mockBcrypt = bcrypt as jest.Mocked<typeof bcrypt>;
const mockJwt = jwt as jest.Mocked<typeof jwt>;

const mockUser = {
  id: 'user-1',
  email: 'alice@example.com',
  name: 'Alice',
  passwordHash: '$2b$12$hashedpw',
  role: 'user' as const,
  createdAt: new Date('2024-01-01'),
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('loginUser', () => {
  it('returns token and refreshToken for valid credentials', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(true);
    (mockJwt.sign as jest.Mock).mockReturnValueOnce('access-token').mockReturnValueOnce('refresh-token');

    const result = await loginUser('alice@example.com', 'password123');

    expect(result).toEqual({ token: 'access-token', refreshToken: 'refresh-token' });
    expect(mockDb.query).toHaveBeenCalledWith(
      expect.stringContaining('WHERE email'),
      ['alice@example.com']
    );
  });

  it('throws when email missing', async () => {
    await expect(loginUser('', 'password')).rejects.toThrow('Email and password required');
  });

  it('throws when password missing', async () => {
    await expect(loginUser('alice@example.com', '')).rejects.toThrow('Email and password required');
  });

  it('throws when both fields missing', async () => {
    await expect(loginUser('', '')).rejects.toThrow('Email and password required');
  });

  it('throws when user not found', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });
    await expect(loginUser('nobody@example.com', 'password')).rejects.toThrow('Invalid credentials');
  });

  it('throws when password wrong', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(false);
    await expect(loginUser('alice@example.com', 'wrongpassword')).rejects.toThrow('Invalid credentials');
  });

  it('propagates DB error', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('connection refused'));
    await expect(loginUser('alice@example.com', 'password')).rejects.toThrow('connection refused');
  });

  it('does not call bcrypt when user not found (short-circuit)', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });
    await expect(loginUser('nobody@example.com', 'password')).rejects.toThrow();
    expect(mockBcrypt.compare).not.toHaveBeenCalled();
  });

  it('handles null email', async () => {
    await expect(loginUser(null as any, 'password')).rejects.toThrow('Email and password required');
  });

  it('handles null password', async () => {
    await expect(loginUser('alice@example.com', null as any)).rejects.toThrow('Email and password required');
  });

  it('signs token with user id and role', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(true);
    (mockJwt.sign as jest.Mock).mockReturnValue('tok');

    await loginUser('alice@example.com', 'password');

    expect(mockJwt.sign).toHaveBeenCalledWith(
      { sub: mockUser.id, role: mockUser.role },
      expect.any(String),
      { expiresIn: '1h' }
    );
  });

  it('signs refresh token with 7d expiry', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    (mockBcrypt.compare as jest.Mock).mockResolvedValue(true);
    (mockJwt.sign as jest.Mock).mockReturnValue('tok');

    await loginUser('alice@example.com', 'password');

    expect(mockJwt.sign).toHaveBeenCalledWith(
      { sub: mockUser.id },
      expect.any(String),
      { expiresIn: '7d' }
    );
  });
});

describe('refreshToken', () => {
  it('returns new access token for valid refresh token', async () => {
    (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1' });
    (mockJwt.sign as jest.Mock).mockReturnValue('new-access-token');

    const result = await refreshToken('valid-refresh-token');

    expect(result).toEqual({ token: 'new-access-token' });
    expect(mockJwt.verify).toHaveBeenCalledWith('valid-refresh-token', expect.any(String));
  });

  it('throws for invalid token', async () => {
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw new Error('invalid signature'); });
    await expect(refreshToken('bad-token')).rejects.toThrow('invalid signature');
  });

  it('throws for expired token', async () => {
    const expiredError = new Error('jwt expired');
    expiredError.name = 'TokenExpiredError';
    (mockJwt.verify as jest.Mock).mockImplementation(() => { throw expiredError; });
    await expect(refreshToken('expired-token')).rejects.toThrow('jwt expired');
  });

  it('signs new token with 1h expiry', async () => {
    (mockJwt.verify as jest.Mock).mockReturnValue({ sub: 'user-1' });
    (mockJwt.sign as jest.Mock).mockReturnValue('new-tok');

    await refreshToken('valid-refresh-token');

    expect(mockJwt.sign).toHaveBeenCalledWith(
      { sub: 'user-1' },
      expect.any(String),
      { expiresIn: '1h' }
    );
  });
});

describe('getUserById', () => {
  it('returns user when found', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });
    const result = await getUserById('user-1');
    expect(result).toEqual(mockUser);
    expect(mockDb.query).toHaveBeenCalledWith(expect.stringContaining('WHERE id'), ['user-1']);
  });

  it('returns null when not found', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });
    const result = await getUserById('nonexistent');
    expect(result).toBeNull();
  });

  it('propagates DB error', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('timeout'));
    await expect(getUserById('user-1')).rejects.toThrow('timeout');
  });

  it('handles empty string id', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });
    const result = await getUserById('');
    expect(result).toBeNull();
  });
});

describe('getAllUsers', () => {
  it('returns paginated users and total', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [mockUser] })
      .mockResolvedValueOnce({ rows: [{ count: '42' }] });

    const result = await getAllUsers(1, 10);

    expect(result).toEqual({ data: [mockUser], total: 42 });
  });

  it('computes correct offset for page 2', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '0' }] });

    await getAllUsers(2, 10);

    expect(mockDb.query).toHaveBeenCalledWith(
      expect.stringContaining('LIMIT $1 OFFSET $2'),
      [10, 10]
    );
  });

  it('computes offset=0 for page 1', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '0' }] });

    await getAllUsers(1, 5);

    expect(mockDb.query).toHaveBeenCalledWith(
      expect.stringContaining('LIMIT $1 OFFSET $2'),
      [5, 0]
    );
  });

  it('returns total as integer, not string', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '100' }] });

    const result = await getAllUsers(1, 10);
    expect(typeof result.total).toBe('number');
    expect(result.total).toBe(100);
  });

  it('returns empty array when no users', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: '0' }] });

    const result = await getAllUsers(9999, 10);
    expect(result.data).toEqual([]);
    expect(result.total).toBe(0);
  });
});

describe('createUser', () => {
  const input = { email: 'new@example.com', password: 'SecurePass1!', name: 'New User' };

  it('creates and returns user for valid input', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: input.email, name: input.name, role: 'user', created_at: new Date() }] });
    (mockBcrypt.hash as jest.Mock).mockResolvedValue('hashed-pw');

    const result = await createUser(input);

    expect(result.email).toBe(input.email);
    expect(mockBcrypt.hash).toHaveBeenCalledWith(input.password, 12);
  });

  it('throws when email already exists', async () => {
    mockDb.query = jest.fn().mockResolvedValueOnce({ rows: [{ id: 'existing' }] });
    await expect(createUser(input)).rejects.toThrow('Email already registered');
  });

  it('does not store plain password — stores hash', async () => {
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'new-1', email: input.email, name: input.name, role: 'user' }] });
    (mockBcrypt.hash as jest.Mock).mockResolvedValue('bcrypt-hash');

    await createUser(input);

    const insertCall = (mockDb.query as jest.Mock).mock.calls[1];
    expect(insertCall[1]).toContain('bcrypt-hash');
    expect(insertCall[1]).not.toContain(input.password);
  });

  it('propagates bcrypt error', async () => {
    mockDb.query = jest.fn().mockResolvedValueOnce({ rows: [] });
    (mockBcrypt.hash as jest.Mock).mockRejectedValue(new Error('bcrypt failure'));
    await expect(createUser(input)).rejects.toThrow('bcrypt failure');
  });

  it('handles unicode in name', async () => {
    const unicodeInput = { email: 'unicode@example.com', password: 'Pass1!', name: 'أليس' };
    mockDb.query = jest.fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ id: 'u-1', email: unicodeInput.email, name: unicodeInput.name, role: 'user' }] });
    (mockBcrypt.hash as jest.Mock).mockResolvedValue('hash');

    const result = await createUser(unicodeInput);
    expect(result.name).toBe(unicodeInput.name);
  });
});

describe('updateUser', () => {
  it('updates and returns user', async () => {
    const updated = { ...mockUser, name: 'Alice Updated' };
    mockDb.query = jest.fn().mockResolvedValue({ rows: [updated] });

    const result = await updateUser('user-1', { name: 'Alice Updated' });

    expect(result.name).toBe('Alice Updated');
    expect(mockDb.query).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE users'),
      ['Alice Updated', 'user-1']
    );
  });

  it('strips passwordHash from updates (cannot change password via this method)', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    await updateUser('user-1', { name: 'Alice', passwordHash: 'new-hash' } as any);

    const insertArgs = (mockDb.query as jest.Mock).mock.calls[0][1];
    expect(insertArgs).not.toContain('new-hash');
  });

  it('strips role from updates (cannot escalate role via this method)', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [mockUser] });

    await updateUser('user-1', { name: 'Alice', role: 'admin' } as any);

    const queryStr = (mockDb.query as jest.Mock).mock.calls[0][0] as string;
    // RETURNING may include 'role' column — only verify SET clause does not set role
    const setClause = queryStr.substring(0, queryStr.toLowerCase().indexOf('returning'));
    expect(setClause.toLowerCase()).not.toContain('role');
  });
});

describe('deleteUser', () => {
  it('calls DELETE query with correct id', async () => {
    mockDb.query = jest.fn().mockResolvedValue({ rows: [] });

    await deleteUser('user-1');

    expect(mockDb.query).toHaveBeenCalledWith(
      expect.stringContaining('DELETE FROM users'),
      ['user-1']
    );
  });

  it('propagates DB error', async () => {
    mockDb.query = jest.fn().mockRejectedValue(new Error('foreign key violation'));
    await expect(deleteUser('user-1')).rejects.toThrow('foreign key violation');
  });
});

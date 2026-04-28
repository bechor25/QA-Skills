import express from 'express';
import { authRouter } from './routes/auth';
import { usersRouter } from './routes/users';
import { authMiddleware } from './middleware/auth';

export const app = express();
app.use(express.json());

app.use('/auth', authRouter);
app.use('/users', authMiddleware, usersRouter);

if (require.main === module) {
  app.listen(3000, () => console.log('Server running on port 3000'));
}

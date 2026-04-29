import express from 'express';
import { authRouter } from './auth';
import { usersRouter } from './users';

export const app = express();
app.use(express.json());
app.use('/auth', authRouter);
app.use('/users', usersRouter);

if (require.main === module) {
  app.listen(3000, () => console.log('Fixture app running on :3000'));
}

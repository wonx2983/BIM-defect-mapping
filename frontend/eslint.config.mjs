import { FlatCompat } from '@eslint/eslintrc';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const compat = new FlatCompat({ baseDirectory: path.dirname(fileURLToPath(import.meta.url)) });
export default [
  { ignores: ['.next/**', 'public/**', 'node_modules/**', 'next-env.d.ts'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'warn',
      '@next/next/no-img-element': 'off',
    },
  },
];

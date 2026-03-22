import { jest } from '@jest/globals';

// Mock environment variables
process.env.FRED_API_KEY = 'test-api-key';

// Mock console.error to avoid cluttering test output
jest.spyOn(console, 'error').mockImplementation(() => {});
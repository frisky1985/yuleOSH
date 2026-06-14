import type { Config } from "jest";

const config: Config = {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { tsconfig: "tsconfig.json" }],
  },
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "^next/navigation$": "<rootDir>/__mocks__/next-navigation.ts",
    "^next/link$": "<rootDir>/__mocks__/next-link.ts",
  },
  testMatch: ["**/__tests__/**/*.test.ts", "**/__tests__/**/*.test.tsx"],
  transformIgnorePatterns: ["/node_modules/(?!(lucide-react)/)"],
};

export default config;

// Mock for next/navigation
export const useRouter = jest.fn(() => ({
  push: jest.fn(),
  replace: jest.fn(),
  prefetch: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  pathname: "/",
}));

export const usePathname = jest.fn(() => "/");
export const useSearchParams = jest.fn(() => new URLSearchParams());

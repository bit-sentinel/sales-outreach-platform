/**
 * API client – centralized HTTP client with auth, retry, and error handling.
 */

import axios, { type AxiosError, type AxiosRequestConfig } from 'axios';

// In the browser, use relative URLs so Next.js rewrites proxy to the backend.
// In server-side rendering, use the internal Docker URL directly.
const API_BASE_URL =
  typeof window !== 'undefined'
    ? ''
    : process.env.INTERNAL_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Request interceptor – attach JWT token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Singleton refresh promise – prevents concurrent 401s from racing to refresh
let refreshingPromise: Promise<string> | null = null;

// Response interceptor – handle 401 (token refresh) and errors
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) throw new Error('No refresh token');

        // If a refresh is already in-flight, wait for it instead of firing another
        if (!refreshingPromise) {
          refreshingPromise = axios
            .post(`/api/v1/auth/refresh`, { refresh_token: refreshToken })
            .then(({ data }) => {
              localStorage.setItem('access_token', data.data.access_token);
              localStorage.setItem('refresh_token', data.data.refresh_token);
              return data.data.access_token as string;
            })
            .finally(() => {
              refreshingPromise = null;
            });
        }

        const newToken = await refreshingPromise;

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
        }
        return apiClient(originalRequest);
      } catch {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
      }
    }

    return Promise.reject(error);
  }
);

// Typed API helpers
export interface APIResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export async function api<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await apiClient.request<APIResponse<T>>(config);
  return response.data.data;
}

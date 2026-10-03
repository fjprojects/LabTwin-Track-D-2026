import axios from "axios";

export const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api").replace(/\/$/, "");
const client = axios.create();
client.interceptors.request.use(config => {
  const token = sessionStorage.getItem("labtwin_access_token");
  if (token && config.url?.startsWith(`${API}/`)) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
client.interceptors.response.use(response => response, error => {
  // A delayed response from the revoked demo session must not sign out the
  // restored teacher. Only the currently active token can expire this session.
  const active = sessionStorage.getItem("labtwin_access_token");
  if (error.response?.status === 401 && active && error.config?.headers?.Authorization === `Bearer ${active}` && !error.config?.url?.endsWith("/auth/login/") && !error.config?.url?.endsWith("/auth/logout/")) {
    window.dispatchEvent(new Event("labtwin-signout"));
  }
  return Promise.reject(error);
});
export default client;

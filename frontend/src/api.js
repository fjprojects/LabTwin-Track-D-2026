import axios from "axios";

export const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api").replace(/\/$/, "");
// A stalled connection must return control to the interface. A client timeout
// does not cancel server work; refresh its state before repeating a mutation.
const client = axios.create({ timeout: 120000 });
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

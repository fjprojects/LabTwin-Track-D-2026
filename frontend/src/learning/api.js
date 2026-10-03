import api, { API } from "../api";
export const base = `${API}/learning`;
export const errorText = error => {
  if (["ECONNABORTED", "ETIMEDOUT"].includes(error?.code)) return "The request timed out. The server may still be finishing your work. Refresh to check its status before trying again.";
  const message = error?.response?.data?.error;
  return typeof message === "string" && message.trim() ? message.slice(0, 1000) : "Could not finish. Check your connection and refresh before trying again.";
};
export const get = async (path, config) => (await api.get(`${base}/${path}`, config)).data;
export const post = async (path, data = {}, config) => (await api.post(`${base}/${path}`, data, config)).data;

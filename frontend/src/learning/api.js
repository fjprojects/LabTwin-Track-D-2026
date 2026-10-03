import api, { API } from "../api";
export const base = `${API}/learning`;
export const errorText = error => error.response?.data?.error || "Could not finish. Check your connection and retry.";
export const get = async (path, config) => (await api.get(`${base}/${path}`, config)).data;
export const post = async (path, data = {}, config) => (await api.post(`${base}/${path}`, data, config)).data;

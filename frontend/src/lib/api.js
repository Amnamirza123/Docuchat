import { supabase } from "./supabaseClient";

const API_URL = import.meta.env.VITE_API_URL;

async function authHeader() {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet(path) {
  const headers = await authHeader();
  const res = await fetch(`${API_URL}${path}`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost(path, body) {
  const headers = await authHeader();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPatch(path, body) {
  const headers = await authHeader();
  const res = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiDelete(path) {
  const headers = await authHeader();
  const res = await fetch(`${API_URL}${path}`, { method: "DELETE", headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiUpload(path, file) {
  const headers = await authHeader();
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers, // no Content-Type — browser sets multipart boundary automatically
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export { API_URL };
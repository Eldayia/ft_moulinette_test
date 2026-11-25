// Client de l'API publique. Le cookie de session est HttpOnly : il n'est jamais lu ici.
// L'en-tête x-ftm-csrf accompagne toutes les requêtes ; l'API le exige pour toute écriture authentifiée par cookie.
import { goto } from '$app/navigation';

export class ApiError extends Error {
	constructor(
		public status: number,
		public code: string,
		message: string
	) {
		super(message);
	}
}

async function request<T>(method: string, path: string, body?: unknown, redirectOn401 = true): Promise<T> {
	const headers: Record<string, string> = { 'x-ftm-csrf': '1' };
	let payload: BodyInit | undefined;
	if (body instanceof FormData) payload = body;
	else if (body !== undefined) {
		headers['content-type'] = 'application/json';
		payload = JSON.stringify(body);
	}
	const response = await fetch(path, { method, headers, body: payload, credentials: 'same-origin' });
	// Session expirée : retour à la connexion, sauf pendant la vérification de session elle-même et si l'on y est
	// déjà (une navigation vers la même page remonterait le formulaire et effacerait la saisie en cours).
	if (response.status === 401 && redirectOn401 && !path.startsWith('/api/auth/') && location.pathname !== '/login') {
		await goto('/login');
	}
	if (response.status === 204) return undefined as T;
	let data: any = null;
	try {
		data = await response.json();
	} catch {
		// corps vide ou non JSON
	}
	if (!response.ok) {
		throw new ApiError(response.status, data?.error?.code ?? 'http_error', data?.error?.message ?? `Erreur HTTP ${response.status}`);
	}
	return data as T;
}

export const api = {
	get: <T>(path: string) => request<T>('GET', path),
	/** Lecture sans redirection automatique (vérification de session). */
	probe: <T>(path: string) => request<T>('GET', path, undefined, false),
	post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
	del: <T>(path: string) => request<T>('DELETE', path)
};

export type Row = {
	file: string;
	line: number;
	column: number;
	check: string;
	status: string;
	message: string;
	raw_message?: string;
	diagnostics?: { file: string; line: number; column: number; message?: string }[];
};
export type Report = { schema_version: number; module: string; summary: Record<string, number>; results: Row[] };
export type Submission = {
	id: string;
	project: string;
	target: string | null;
	source: string;
	status: string;
	outcome: string | null;
	files: number;
	created_at: string;
	finished_at: string | null;
	duration_seconds: number | null;
	summary: Record<string, number> | null;
	error: { category: string; code: string; message: string } | null;
	report?: Report | null;
	metadata?: Record<string, any> | null;
	options?: Record<string, any>;
	queue_position?: number | null;
};
export type Me = { login: string; is_admin: boolean };
export type Status = {
	executions_enabled: boolean;
	message: string | null;
	projects: string[];
	limits: { max_upload_bytes: number; max_files: number; max_file_bytes: number; submission_timeout: number };
	quotas: { per_user_daily: number; per_user_concurrent: number };
};

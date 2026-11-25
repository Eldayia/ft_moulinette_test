import { api, type Me, type Status } from './api';

// État partagé de la session (Svelte 5 : runes dans un module .svelte.ts).
export const session = $state<{ me: Me | null; status: Status | null; ready: boolean }>({
	me: null,
	status: null,
	ready: false
});

export async function refreshSession() {
	try {
		session.me = await api.probe<Me>('/api/me');
		session.status = await api.probe<Status>('/api/status');
	} catch {
		session.me = null;
	}
	session.ready = true;
}

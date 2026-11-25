import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Application monopage servie par nginx : aucun serveur Node en production.
			adapter: adapter({ fallback: '200.html', precompress: false }),
			// CSP en balise meta : empreintes des scripts de démarrage, aucune source externe.
			// frame-ancestors (ignoré en meta) est envoyé par nginx.
			csp: {
				mode: 'hash',
				directives: {
					'default-src': ['self'],
					'script-src': ['self'],
					'style-src': ['self'],
					// Seul attribut style autorisé : celui de l'annonceur de navigation de SvelteKit (accessibilité).
					'style-src-attr': ['unsafe-hashes', 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='],
					'img-src': ['self', 'data:'],
					'connect-src': ['self'],
					'object-src': ['none'],
					'base-uri': ['none'],
					'form-action': ['self']
				}
			}
		})
	],
	server: {
		// Développement : l'API FastAPI tourne sur le port 8000.
		proxy: { '/api': 'http://127.0.0.1:8000' }
	}
});

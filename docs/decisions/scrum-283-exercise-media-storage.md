# SCRUM-283: Exercise media storage

## Status

Accepted for local development on 2026-11-20.

## Decision

Exercise thumbnails and animations are stored in the Cloudflare R2 bucket
`taeplando-zpi` in the Eastern Europe location. R2 is accessed through its
S3-compatible API.

The bucket connection values are:

- S3 endpoint: `https://f8dde3cdcdf372feffa256d00f911a59a.r2.cloudflarestorage.com`
- bucket name: `taeplando-zpi`
- region: `auto`
- public base URL: `https://pub-4f30165a7684432f975ffe8c15885c00.r2.dev`

The S3 endpoint intentionally excludes the bucket name. S3 clients receive the
bucket name separately.

Each exercise has exactly one thumbnail and one animation. Object keys use the
stable exercise identifier together with a readable slug:

```text
exercises/{exercise_id}-{slug}/thumb.webp
exercises/{exercise_id}-{slug}/anim.webp
```

The local frontend reads these objects through the public `r2.dev` URL. The
media are public application assets, so read requests do not use presigned
URLs. The development URL is rate-limited and is not the selected solution for
a future production deployment; production requires a separate decision about
a custom domain.

Only the backend or the media upload script receives R2 credentials. The R2 API
token must be limited to the `taeplando-zpi` bucket and use the `Object Read &
Write` permission. Cloudflare does not offer a durable write-only R2 token; the
additional read permission does not expose private data because the selected
objects are already public. Credentials must not be committed or exposed to the
frontend.

No CORS policy is configured. The local frontend renders the public WebP URLs
directly and does not read them with `fetch`, canvas, or other JavaScript APIs
that require cross-origin access. A CORS policy must be added if that access
pattern changes.

## Out of scope

This infrastructure decision does not:

- upload or seed media files (SCRUM-284),
- change exercise database models or API schemas (SCRUM-284),
- render thumbnails or animations in the frontend (SCRUM-285),
- provide the operational media-management guide or screenshots (SCRUM-286),
- create or modify the media assets themselves (SCRUM-282).

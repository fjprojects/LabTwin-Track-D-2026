# Durable LabTwin on Render Free + Supabase Free

**Candidate only.** No production Supabase connection, live migration, media upload, Render change or restart acceptance test has run.

## Architecture

LabTwin's Django accounts, classrooms, assessments, mastery and source metadata
move from temporary SQLite to Supabase PostgreSQL. Original course files and
extracted figures use the existing private FileField factory, now optionally
backed by the private Supabase S3 bucket named labtwin-private-materials.

A disposable local cache in /data/cloud_file_cache downloads originals only
when the existing PDF/OCR/FFmpeg extractor or authenticated PDF viewer needs
them. It is safe for this cache to vanish. Chroma vectors are restored at
startup from source embeddings stored in PostgreSQL using the
restore_course_vectors management command. If vector rebuilding fails, the
existing SQL-grounded lexical retrieval remains a fallback.

The storage bucket must remain Private. Browser code never receives S3 keys
or public S3 object URLs. Signed LabTwin source links still check the classroom
and LabTwin session for every request.

## Required private environment configuration

Set all variables together in a separately authorized test environment before
any live Render cutover:

| Variable | Value |
| --- | --- |
| LABTWIN_DATABASE_URL | Supabase Postgres Session pooler URI, port 5432, URL-encoded password |
| LABTWIN_S3_ENDPOINT | Supabase HTTPS S3 endpoint, like https://PROJECT_REF.storage.supabase.co/storage/v1/s3 |
| LABTWIN_S3_REGION | The S3 region shown by Supabase, normally ap-south-1 for Mumbai |
| LABTWIN_S3_BUCKET | labtwin-private-materials |
| LABTWIN_S3_ACCESS_KEY_ID | Generated server-side S3 key ID |
| LABTWIN_S3_SECRET_ACCESS_KEY | Generated server-side S3 secret |

In Supabase open Storage > Configuration > S3, enable S3 and generate an access
key pair. S3 server keys bypass Supabase storage RLS: never put them into
public code, GitHub, screenshots, chat, or a VITE-prefixed variable. Keep the
existing DJANGO_SECRET_KEY and LABTWIN_DEPLOYMENT_PASSWORD unchanged.

This deployment refuses partial cloud configuration. Supabase Free's maximum
50 MB single-file limit is enforced in cloud mode. The Free project may pause
when idle. The PostgreSQL database and files are durable across Render restarts,
but some legacy scratch/session files under /data remain temporary.

## Required validation before deployment

1. Use this isolated candidate branch, not the live Render branch.
2. Run the original backend tests and new offline tests:
   python backend/manage.py test deployment.test_persistence --noinput
   Run fresh Django migrations, migration-drift check, frontend tests/build/lint.
3. With authorized test credentials, run Django migrations into Supabase public
   schema and test user signup/signin and classroom enrollment.
4. Upload a test PDF; verify status Ready, page extraction, private source
   citation, PDF rendering, unauthorized access denial, and original in S3.
5. Restart the test server and clear only its disposable cache; verify the same
   accounts, PDFs, citations, mastery, evaluations and assessments survived.
   Verify the vector restore logs.
6. Test expired access links, upload-size rejection, S3 outage, credentials
   rotation, private-bucket setting, file deletion and provider quota limits.
7. Only then request explicit approval to deploy to the existing Free Render
   service. This integration does not automatically move old SQLite data.
   If current SQLite contains valuable data, obtain verified backups and migrate
   the data before any cutover.

## Limitations

- The first access to a large PDF after restart downloads a local copy.
- Database rows and S3 objects aren't a single atomic transaction; a failed
  SQL transaction can leave an orphan object needing cleanup.
- Some legacy /data scratch files still disappear after server restart.
- Staging Supabase connectivity, browser checks and restart persistence have
  NOT been tested. Offline tests alone do not prove the deployment is ready.

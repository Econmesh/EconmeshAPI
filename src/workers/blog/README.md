# Blog worker

Publishes scheduled blog posts when `publish_at` is due.

```bash
poetry run python -m src.workers.blog.runner
```

Polls MongoDB every 60 seconds for posts with `status=scheduled` and
`publish_at <= now`, then flips them to `published`.

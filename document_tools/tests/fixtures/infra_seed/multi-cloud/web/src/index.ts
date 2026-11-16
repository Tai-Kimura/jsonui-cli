import OpenAI from "openai";
import { S3Client } from "@aws-sdk/client-s3";
import { kv } from "@vercel/kv";
import * as Sentry from "@sentry/nextjs";

const redisUrl = process.env.REDIS_URL;
const dsn = process.env.SENTRY_DSN;
export const client = new OpenAI();
export const s3 = new S3Client({});
export { kv, Sentry, redisUrl, dsn };

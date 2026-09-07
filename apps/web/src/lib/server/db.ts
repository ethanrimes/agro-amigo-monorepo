import "server-only";
import { Pool, types } from "pg";
types.setTypeParser(1700, Number);
types.setTypeParser(20, Number);
types.setTypeParser(1082, (value) => value);
const globalForDb = globalThis as unknown as { agroPool?: Pool };
export function database() {
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_NOT_CONFIGURED");
  if (!globalForDb.agroPool) {
    globalForDb.agroPool = new Pool({
      connectionString: process.env.DATABASE_URL,
      ssl:
        process.env.DATABASE_SSL === "false"
          ? false
          : { rejectUnauthorized: true },
      max: 5,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 8000,
      statement_timeout: 15000,
    });
    globalForDb.agroPool.on("error", () =>
      console.error("Database connection interrupted"),
    );
  }
  return globalForDb.agroPool;
}
export const WINDOW =
  "observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

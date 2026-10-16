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
      // Every CURRENT_DATE cutoff must agree with Colombia's displayed day,
      // including the hours after UTC midnight and before Bogotá midnight.
      options: "-c timezone=America/Bogota",
      ssl:
        process.env.DATABASE_SSL === "false"
          ? false
          : { rejectUnauthorized: true },
      // Four bounded connections allow the two historical catalog readers
      // to run alongside interactive product and source reads.
      max: 4,
      idleTimeoutMillis: 30000,
      // A busy pool may queue a fast read behind bounded historical
      // queries. Allow that wait without extending the SQL execution deadline.
      connectionTimeoutMillis: 30000,
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

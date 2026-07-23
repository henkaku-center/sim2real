import { defineConfig } from "vite";

export default defineConfig({
  // models/sesame.xml is imported ?raw from the repo root so the browser and
  // native Python run the exact same MJCF (single source of truth).
  server: {
    fs: { allow: [".."] },
  },
  worker: {
    format: "es",
  },
  optimizeDeps: {
    exclude: ["@mujoco/mujoco"],
  },
});

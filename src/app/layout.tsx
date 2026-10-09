import type { Metadata } from "next";
import "./globals.css";
import "@/features/creative/workbench.css";
import { AppShell } from "@/components/AppShell";
export const metadata: Metadata = {
  title: "CineAI Studio · AI 短剧创作工作台",
  description: "让每一个灵感，成为下一幕。AI 剧本、分镜与 3D 导演工作台。",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

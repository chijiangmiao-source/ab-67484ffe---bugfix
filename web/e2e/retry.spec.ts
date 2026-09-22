import { expect, test } from "@playwright/test";

test("失败后保留待重试操作，恢复后取回唯一镜号，且后续号码无缺口", async ({
  page,
}) => {
  const scene = `e2e-retry-${Date.now()}`;
  await page.goto("/");

  await page.getByLabel("场次").fill(scene);
  await page.getByLabel("备注").fill("开场航拍");
  await page.getByLabel(/注入提交后故障/).check();
  await page.getByRole("button", { name: "领取镜号" }).click();

  // 服务端“提交后崩溃”：页面给出失败反馈并保留待重试操作
  await expect(page.getByTestId("error-unavailable")).toBeVisible();
  await expect(page.getByTestId("pending-banner")).toBeVisible();

  // 刷新页面，待重试操作仍在
  await page.reload();
  await expect(page.getByTestId("pending-banner")).toBeVisible();
  await expect(page.getByLabel("场次")).toHaveValue(scene);

  // 恢复后重试：取回最初分配的镜号 1（重放，不重复占号）
  await page.getByRole("button", { name: /重试领取镜号/ }).click();
  await expect(page.getByTestId("result-card")).toContainText("镜号 #1");
  await expect(page.getByTestId("result-card")).toContainText("重放结果");
  await expect(page.getByTestId("pending-banner")).toHaveCount(0);

  // 下一个新操作拿到连续的 2 号
  await page.getByLabel(/注入提交后故障/).uncheck();
  await page.getByLabel("备注").fill("第二条");
  await page.getByRole("button", { name: "领取镜号" }).click();
  await expect(page.getByTestId("result-card")).toContainText("镜号 #2");
  await expect(page.getByTestId("issued-row")).toHaveCount(2);
});

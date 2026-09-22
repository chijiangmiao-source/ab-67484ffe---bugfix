import { expect, test } from "@playwright/test";

test("同一操作标识换内容给出 409 冲突反馈，可作为新操作重新提交", async ({
  page,
}) => {
  const scene = `e2e-conflict-${Date.now()}`;
  await page.goto("/");

  await page.getByLabel("场次").fill(scene);
  await page.getByLabel("备注").fill("版本A");
  await page.getByLabel(/注入提交后故障/).check();
  await page.getByRole("button", { name: "领取镜号" }).click();
  await expect(page.getByTestId("error-unavailable")).toBeVisible();

  // 保留同一操作标识，修改内容后重试 -> 冲突反馈
  await page.getByLabel(/注入提交后故障/).uncheck();
  await page.getByLabel("备注").fill("版本B");
  await page.getByRole("button", { name: /重试领取镜号/ }).click();
  await expect(page.getByTestId("error-conflict")).toBeVisible();
  await expect(page.getByTestId("error-conflict")).toContainText("冲突");

  // 以新操作重新提交：版本A 已占 1 号，版本B 拿到连续的 2 号
  await page.getByRole("button", { name: "以新操作重新提交" }).click();
  await expect(page.getByTestId("result-card")).toContainText("镜号 #2");
  await expect(page.getByTestId("issued-row")).toHaveCount(2);
});

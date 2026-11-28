"""Headless Chromium UI smoke and employee->admin->employee request round-trip.

All browser interactions use local ephemeral test database, never live BID records.
"""
import asyncio
import os
from playwright.async_api import async_playwright

BASE="http://127.0.0.1:8000"
ADMIN_VIEWS=["dashboard","organization","employees","requests","shifts","travel",
             "meals","approvalCenter","groupReport","reports","corrections","quality",
             "payroll","exports","legal","legalMonitor","holidays","terminal","accounts"]

async def login(page,username,password):
    await page.goto(BASE+"/",wait_until="domcontentloaded")
    await page.locator("#username").fill(username)
    await page.locator("#password").fill(password)
    await page.locator("#loginForm button[type=submit]").click()
    await page.locator("#app:not(.hidden)").wait_for(timeout=25000)
    await page.wait_for_timeout(500)

async def admin_nav(page,view):
    await page.locator('.sidebar .nav[data-view="'+view+'"]').click()
    await page.wait_for_timeout(700)
    assert await page.locator("#content").count(),f"Admin view missing: {view}"
    error=page.locator("#content > .error")
    if await error.count() and await error.is_visible():
        raise AssertionError(f"Admin view {view}: {(await error.inner_text())[:300]}")
    print("ADMIN_VIEW_OK",view,flush=True)

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        a=await browser.new_context(viewport={"width":1360,"height":920},locale="sk-SK")
        w=await browser.new_context(viewport={"width":390,"height":844},is_mobile=True,
                                    has_touch=True,locale="sk-SK")
        admin=await a.new_page()
        employee=await w.new_page()
        failures=[]
        for page,label in [(admin,"admin"),(employee,"employee")]:
            page.on("pageerror",lambda e,label=label: failures.append((label,str(e))))
        await login(admin,os.environ["BOOTSTRAP_ADMIN_USERNAME"],os.environ["BOOTSTRAP_ADMIN_PASSWORD"])
        await login(employee,"demo.zamestnanec",os.environ["DEMO_EMPLOYEE_PASSWORD"])

        # Navigate all 19 administrator sections to catch broken module links.
        for view in ADMIN_VIEWS:
            await admin_nav(admin,view)

        # Verify employee UI: mobile bottom bar and calendar are touch operable.
        await employee.locator('#mobileBottomNav [data-mobile-tab="requests"]').click()
        await employee.locator("#bid-request-form").wait_for(timeout=12000)
        assert not await employee.locator('.sidebar .nav[data-view="employees"]').is_visible()
        await employee.locator('#bid-request-form [name="kind"]').select_option("vacation")
        await employee.locator('#bid-request-form [name="start"]').fill("2027-06-08")
        await employee.locator('#bid-request-form [name="end"]').fill("2027-06-08")
        await employee.locator('#bid-request-form [name="note"]').fill("UI end-to-end demonstration")
        await employee.locator('#bid-request-form button[type=submit]').click()
        await employee.locator(".bid-request-success").wait_for(timeout=20000)
        status=await employee.locator(".bid-request-success").inner_text()
        assert "Žiadosť" in status and "Čaká" in status,status
        print("EMPLOYEE_SUBMIT_OK",flush=True)

        await admin_nav(admin,"requests")
        row=admin.locator("#content tbody tr").filter(has_text="2027-06-08").filter(has_text="Filip Ukážkový")
        assert await row.count()==1,f"New request not found or duplicated, matches: {await row.count()}"
        assert "pending" in await row.inner_text()
        await row.locator("[data-approve]").click()
        await admin.locator("#content tbody tr").filter(has_text="2027-06-08").filter(has_text="Filip Ukážkový").locator(".pill.approved").wait_for(timeout=20000)
        print("ADMIN_APPROVAL_OK",flush=True)

        # Employee refreshes own requests, which must now display approved.
        await employee.locator('#mobileBottomNav [data-mobile-tab="requests"]').click()
        await employee.locator('.bid-request-history-item').filter(has_text="2027-06-08").locator('.bid-day-tag-approved').wait_for(timeout=20000)
        await employee.locator('[data-cal-day="2027-06-08"]').click()
        assert "Schválené" in await employee.locator("#bid-requests-detail").inner_text()
        print("EMPLOYEE_APPROVAL_VISIBLE_OK",flush=True)

        # Admin monthly calendar shows same employee/day as employee report.
        await admin_nav(admin,"reports")
        await admin.locator("#empSelect").select_option(label="Filip Ukážkový")
        await admin.locator("#reportFrom").fill("2027-06-01")
        await admin.locator("#reportFrom").dispatch_event("change")
        await admin.locator('[data-cal-day="2027-06-08"]').wait_for(timeout=20000)
        await admin.locator('[data-cal-day="2027-06-08"]').click()
        assert "jún" in (await admin.locator("#bid-admin-day").inner_text()).lower()
        print("ADMIN_CALENDAR_DAY_OK",flush=True)

        await employee.locator('#mobileBottomNav [data-mobile-tab="reports"]').click()
        await employee.locator(".bid-calendar-panel").wait_for(timeout=16000)
        print("EMPLOYEE_CALENDAR_OK",flush=True)

        if failures:
            raise AssertionError("Browser JavaScript errors: "+str(failures[:8]))
        await browser.close()

if __name__=="__main__":
    asyncio.run(main())

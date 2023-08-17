const puppeteer = require('puppeteer');
const fs = require('fs');

function delay(millis) {
  return new Promise((resolve, reject) => setTimeout(a => resolve(), millis));
}

(async () => {
  const browser = await puppeteer.launch({headless: true});
  const page = await browser.newPage();
  await page.setViewport({
    width: 800,
    height: 600,
    deviceScaleFactor: 1
  })
  await page.setUserAgent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36");

  const mainUrl = "https://mobile.citybus.com.hk/nwp3/?f=1&ds=&dsmode=1&l=0";
  await page.goto(mainUrl);

  let routeIdsResult = {};

  await page.waitForSelector('[onclick*="search_cookie(\'X\',document.ksearch.skey.value,0);"]');
  await page.click('[onclick*="search_cookie(\'X\',document.ksearch.skey.value,0);"]');

  await page.waitForSelector('#routesearchitemlist');
  await page.screenshot({ path: 'screenshot.png' });

  let tdElements = await page.$$('#routesearchitemlist td[onclick*="showvariance1"]');

  for (let i = 0; i < tdElements.length; i++) {
    try {
      console.log((i + 1) + " of " + tdElements.length);
      let tdElement = tdElements[i];
      await page.evaluate((selector, j) => {
        const scrollableSection = document.querySelector(selector);
        scrollableSection.scrollTop = 50.625 * j;
      }, "#routelist2", i);
      await tdElement.click();

      const identifier = '[onclick*="showroute1"]';
      await page.waitForSelector(identifier);
      let targetElements = await page.$$(identifier);

      for (let u = 0; u < targetElements.length; u++) {
        try {
          let targetElement = targetElements[u];
          const lineElement = await targetElement.evaluate((element) => {
            const onclickValue = element.getAttribute('onclick');
            const match = /.*showroute1\('(.*)',.*/g.exec(element.getAttribute('onclick'));
            if (match) {
              return match;
            }
            return null;
          });
          if (targetElements.length == 1) {
            await delay(1000);
            await page.click('[onclick*="backsearch"]');
            await delay(500);
            await page.waitForSelector(identifier);
            targetElements = await page.$$(identifier);
            targetElement = targetElements[u];
          }
          await targetElement.click();

          await delay(2000);
          let closeBlockClick = await page.$('[onclick*="hidespecialNote"]');
          if (closeBlockClick) {
            const isVisible = await closeBlockClick.evaluate((el) => {
              const style = window.getComputedStyle(el);
              return style && style.display !== 'none' && style.visibility !== 'hidden';
            });
            if (isVisible) {
              await closeBlockClick.click();
            }
          }

          await page.waitForSelector(`[onclick*="showtimetable1"]`);
          const timetableElement = await page.evaluate(() => {
            const elements = document.querySelectorAll('[onclick]');
            for (const element of elements) {
              const match = /.*showtimetable1\('(.*)','(.*)',(.*)\).*/g.exec(element.getAttribute('onclick'));
              if (match) {
                return match;
              }
            }
            return null;
          });

          let [, id, bound] = timetableElement;
          let route = /.*\|\|([A-Z0-9]+)\-.*/g.exec(id)[1];
          let londId = lineElement[1];
          let variant = londId.split("||")[0];
          console.log('Route:', route);
          console.log('Id:', id);
          console.log('Bound:', bound);
          console.log('Variant:', variant);
          console.log('LongId:', londId);

          if (!routeIdsResult.hasOwnProperty(route)) {
            routeIdsResult[route] = {};
          }
          if (!routeIdsResult[route].hasOwnProperty(bound)) {
            routeIdsResult[route][bound] = {"id": id, "main-variant": variant, "variants": {}};
          } else if (routeIdsResult[route][bound]["main-variant"] > variant) {
            routeIdsResult[route][bound]["main-variant"] = variant;
            routeIdsResult[route][bound]["id"] = id;
          }
          routeIdsResult[route][bound]["variants"][variant] = {"id": id, "longId": londId};
        } catch (error) {
          console.error(error);
        } finally {
          await page.click('[onclick*="backsearch"]');
          await delay(500);
          await page.waitForSelector(identifier);
          targetElements = await page.$$(identifier);
        }
      }
    } catch (error) {
      console.error(error);
      i--;
      await page.screenshot({ path: 'error.png' });
    } finally {
      let json = JSON.stringify(routeIdsResult, null, 4);
      fs.writeFile('ctb_route_ids_temp.json', json, 'utf8', e => {});

      while (true) {
        try {
          try {
            await page.click('[onclick*="backsearch"]');
          } catch (error) {
            console.error(error);
            await page.goto(mainUrl);
            await page.waitForSelector('[onclick*="search_cookie(\'X\',document.ksearch.skey.value,0);"]');
            await page.click('[onclick*="search_cookie(\'X\',document.ksearch.skey.value,0);"]');
            await delay(2000);
          }
          await delay(500);
          await page.waitForSelector('#routesearchitemlist');
          tdElements = await page.$$('#routesearchitemlist td[onclick*="showvariance1"]');
          await page.screenshot({ path: 'screenshot.png' });
          break;
        } catch (error) {
          console.error(error);
        }
      }
    }
  }

  await page.screenshot({ path: 'screenshot.png' });

  await browser.close();

  let json = JSON.stringify(routeIdsResult, null, 4);
  fs.mkdir('data', { recursive: true }, (err) => {});
  fs.writeFile('data/ctb_route_ids.json', json, 'utf8', e => {});
})();
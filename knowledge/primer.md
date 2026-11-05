# Fed primer

Background for Fed Decoder's Ask assistant. Every section is written from the official pages listed under it (snapshots in `knowledge/sources/`, refreshed monthly by `scripts/build_primer.py`). This file holds no names of sitting officials and no present-day rates: those always come from live tools.

## Why the Fed exists

The Federal Reserve is the central bank of the United States. Congress created it to give the country a safer, more flexible and more stable monetary and financial system; President Woodrow Wilson signed the Federal Reserve Act on December 23, 1913. After the Panic of 1907, the United States was the only major financial power without a central bank and had to turn to Wall Street financiers to stop the crisis.

The Fed's work falls into four areas:
- **Monetary policy:** influencing money and credit conditions in pursuit of full employment and stable prices.
- **Supervision:** overseeing banks and other important financial institutions for safety and soundness, and protecting consumers' credit rights.
- **Financial stability:** containing risks that can spread through financial markets.
- **Payments and services:** acting as a bank for the U.S. government and banks, and running key parts of the payment system.

Sources: [Purpose of the Fed (FAQ)](https://www.federalreserve.gov/faqs/about_12594.htm) · [Federal Reserve Act signed](https://www.federalreservehistory.org/essays/federal-reserve-act-signed)

## The mandate

The Federal Reserve Act tells the Fed to promote "maximum employment, stable prices, and moderate long-term interest rates." Because stable prices and strong employment tend to bring moderate long-term rates with them, the goals are usually called the **dual mandate**.

- **Maximum employment** is the highest level of employment the economy can sustain without pushing up inflation. The Fed sets no fixed number for it, because it depends on things monetary policy can't control, such as how the labor market is structured.
- **Stable prices** means people can plan, borrow and lend without worrying that costs will jump or fall. The FOMC judges that **2 percent inflation over the longer run, measured by the PCE price index**, is most consistent with both goals.
- The FOMC explains its approach in the Statement on Longer-Run Goals and Monetary Policy Strategy, first published in 2012 and revised after public reviews in 2020 and 2025. It plans a review about every five years.

Sources: [Monetary policy: goals and how it works](https://www.federalreserve.gov/monetarypolicy/monetary-policy-what-are-its-goals-how-does-it-work.htm) · [Economic goals (FAQ)](https://www.federalreserve.gov/faqs/what-economic-goals-does-federal-reserve-seek-to-achieve-through-monetary-policy.htm) · [Why 2 percent (FAQ)](https://www.federalreserve.gov/faqs/economy_14400.htm) · [Longer-run goals statement (FAQ)](https://www.federalreserve.gov/faqs/statement-on-longer-run-goals-monetary-policy-strategy-FOMC.htm)

## Structure: who does what

- **Board of Governors.** A federal agency in Washington, D.C., with seven members, each appointed by the President and confirmed by the Senate. Governors serve staggered **14-year terms**. The Chair and Vice Chairs are chosen from among the governors for **4-year terms** in those roles. Elected officials can't serve on the Board. The Board oversees the Reserve Banks, sets the interest rate on reserve balances, and shares bank supervision with the Reserve Banks.
- **12 Federal Reserve Banks.** Regional banks around the country. They run the discount window, supervise banks in their districts, and report on local economic conditions. Each president is appointed by the bank's non-banker directors, subject to the Board's approval.
- **Federal Open Market Committee (FOMC).** The body that sets monetary policy. It has **12 voters**: the 7 governors, the president of the New York Fed (always a voter, and the Committee's vice chair), and 4 of the other 11 Reserve Bank presidents, who rotate in one-year terms. The Board Chair chairs the FOMC. All 12 presidents attend and join the discussion; only the voters vote.

The Fed is "independent within the government." It doesn't get money from Congress (its income is mainly interest on securities it holds, and it sends the surplus to the Treasury), and long staggered terms shield decisions from short-term politics. It is accountable to Congress: the Chair testifies, and the Board sends a Monetary Policy Report twice a year.

Sources: [Who we are](https://www.federalreserve.gov/aboutthefed/fedexplained/who-we-are.htm) · [FOMC (FAQ)](https://www.federalreserve.gov/faqs/about_12844.htm) · [Independence (FAQ)](https://www.federalreserve.gov/faqs/about_12799.htm) · [Selecting a Reserve Bank president (FAQ)](https://www.federalreserve.gov/faqs/how-is-a-federal-reserve-bank-president-selected.htm) · [Legal framework (FAQ)](https://www.federalreserve.gov/faqs/basic-framework-determines-conduct-monetary-policy.htm)

## The tools

- **Federal funds rate target.** The FOMC's main lever. The federal funds rate is what banks pay to borrow reserve balances from each other overnight. The FOMC sets a target range for it.
- **Interest on reserve balances (IORB).** The rate the Fed pays banks on money they keep at the Fed. A bank won't lend for less than it can earn at the Fed, so moving this rate pulls the federal funds rate into the target range. It's the main way the target is put into practice, because reserves are abundant.
- **Overnight reverse repo facility (ON RRP).** A backstop that sets a floor for money market funds and other firms that can't earn IORB: the Fed sells them a security and buys it back the next day.
- **Open market operations.** Buying and selling securities. Before 2008 these fine-tuned the supply of reserves. From late 2008 to 2014 the Fed bought large amounts of longer-term securities ("quantitative easing," QE) to push down long-term rates. Letting holdings run off or shrink is "quantitative tightening" (QT).
- **The balance sheet** shows those holdings (Treasury and agency mortgage-backed securities) and what funds them (reserves, currency, reverse repos).
- **Discount window.** Short-term loans from the Reserve Banks to banks, mainly "primary credit" to sound banks. It's how the Fed acts as lender of last resort.
- **Forward guidance.** Statements about the likely future path of rates. Long-term rates depend on expectations, so guidance itself moves borrowing costs.

Sources: [Policy tools](https://www.federalreserve.gov/monetarypolicy/policytools.htm) · [Interest on reserve balances](https://www.federalreserve.gov/monetarypolicy/reserve-balances.htm) · [ON RRP](https://www.federalreserve.gov/monetarypolicy/overnight-reverse-repurchase-agreements.htm) · [Open market operations](https://www.federalreserve.gov/monetarypolicy/openmarket.htm) · [Discount window](https://www.federalreserve.gov/monetarypolicy/discountrate.htm) · [Balance sheet](https://www.federalreserve.gov/monetarypolicy/bst.htm)

## How policy reaches people

- **Short-term borrowing.** Changes in the federal funds rate show up quickly in Treasury bills, floating-rate loans and credit lines.
- **Prime rate and credit cards.** Banks set their own prime rate, but most base it on the federal funds target. Many credit cards and small-business loans are priced off prime, so their rates tend to follow the Fed's moves.
- **Mortgages and other long-term loans.** Fixed-rate mortgages depend on expectations for rates over many years, not on this month's decision. They move with longer-term Treasury yields, especially the 10-year, and can move before the Fed acts, or the opposite way.
- **Savings.** Yields on savings accounts and money market funds are short-term rates, so they tend to follow the federal funds rate, usually only partly.
- **Stocks, the dollar and jobs.** Higher rates make stocks relatively less attractive, can strengthen the dollar by drawing money into U.S. assets, and cool spending and hiring. Lower rates do the reverse.

Sources: [Monetary policy: goals and how it works](https://www.federalreserve.gov/monetarypolicy/monetary-policy-what-are-its-goals-how-does-it-work.htm) · [Prime rate (FAQ)](https://www.federalreserve.gov/faqs/credit_12846.htm) · [Why interest rates matter (FAQ)](https://www.federalreserve.gov/faqs/why-do-interest-rates-matter.htm)

## How the Fed communicates

- **Meeting cycle.** Eight scheduled FOMC meetings a year, about every six weeks, plus unscheduled ones when needed. Each scheduled meeting ends with a **statement** (the decision, the outlook and the vote) and a press conference by the Chair.
- **Minutes** come out three weeks later and summarize the debate, including each member's vote. **Transcripts** are released after about five years.
- **Summary of Economic Projections (SEP).** Four times a year, each participant projects growth, unemployment, inflation and the appropriate policy rate for the next few years and the longer run. The rate projections, one dot per participant, make up the **dot plot**. Dots are individual views, not a plan or a promise.
- **Dissents** are votes against the decision, published with the vote. They show where the debate is heading.

Sources: [FOMC (FAQ)](https://www.federalreserve.gov/faqs/about_12844.htm) · [SEP (FAQ)](https://www.federalreserve.gov/faqs/summary-economic-projections-sep.htm) · [Minutes (FAQ)](https://www.federalreserve.gov/faqs/minutes-federal-open-market-committee-fomc.htm) · [Balance sheet and transparency](https://www.federalreserve.gov/monetarypolicy/bst.htm)

## Key eras

- **The Great Inflation and the Volcker years (1965–1982).** Inflation climbed for nearly two decades. Paul Volcker became Chair in August 1979 with inflation above 11 percent. In October 1979 the FOMC switched to targeting reserve growth and let rates rise as far as needed. Rates spiked, and the economy went through recessions in 1980 and 1981–82, with unemployment near 11 percent at the peak; by late 1982 inflation was back under 5 percent. The lesson: price stability supports both parts of the mandate.
- **The 2008 financial crisis.** As the housing bust turned into a financial crisis, the FOMC cut its target from 4.5 percent at the end of 2007 to a range of 0 to 0.25 percent by December 2008. It then used large-scale asset purchases and forward guidance, and kept rates exceptionally low for years as the recovery stayed weak.
- **The 2020 pandemic.** On March 15, 2020, in an emergency meeting, the FOMC cut its target range to 0 to 0.25 percent and announced purchases of at least $500 billion of Treasuries and $200 billion of mortgage-backed securities.
- **The 2022–23 hikes.** To bring high inflation back to 2 percent, the FOMC raised rates at a run of meetings from March 16, 2022 (to 0.25–0.5 percent) through July 26, 2023 (to 5.25–5.5 percent).

For any meeting since 2000, the decision, vote and statement come from the meeting archive tools, not this primer.

Sources: [The Great Inflation](https://www.federalreservehistory.org/essays/great-inflation) · [The Great Recession and its aftermath](https://www.federalreservehistory.org/essays/great-recession-and-its-aftermath) · [FOMC statement, March 15, 2020](https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm) · [FOMC statement, March 16, 2022](https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm) · [FOMC statement, July 26, 2023](https://www.federalreserve.gov/newsevents/pressreleases/monetary20230726a.htm)

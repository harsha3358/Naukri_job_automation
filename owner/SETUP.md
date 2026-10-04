# For the owner: see who is using the tool

This is a one-time setup done by you, the owner. It is not for your users.

After it, every person who continues past the first welcome step is added to a Google Sheet
that only you can open: date, name, email.

## What your users see

The first welcome step shows this, the same for every user:

> When you click Continue, your **name and email** are sent to the maker of this tool, so they
> know who is using it. Nothing else is sent: not your CV, not your Naukri account, not your
> job applications. To send nothing, use Skip setup.

This line must stay. Collecting people's details without telling them is not allowed under
India's data protection law (DPDP Act, 2023), and it would also break the trust the tool
depends on. A user who clicks **Skip setup** sends nothing.

## Steps

1. Open [sheets.new](https://sheets.new) while signed in to **your** Google account. Name the
   sheet, for example `Naukri Job Automation users`.
2. In the sheet menu, click **Extensions**, then **Apps Script**.
3. Delete whatever is in the editor. Open `owner/collect_users.gs` from this project, copy all
   of it, and paste it in. Click the save icon.
4. Click **Deploy**, then **New deployment**. Click the gear icon and pick **Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone**
5. Click **Deploy**. Google asks you to authorise the script: choose your account, click
   **Advanced**, then **Go to (project name)**, then **Allow**.
6. Copy the **Web app URL**. It starts with `https://script.google.com/macros/s/` and ends
   with `/exec`.
7. Open `backend/config.py` and paste the link between the quotes:

   ```python
   OWNER_REGISTRATION_URL = "https://script.google.com/macros/s/.../exec"
   ```

8. Save, commit and push. Every copy downloaded from now on registers with your sheet.

## Check that it works

Start the tool on your own PC, go through the first welcome step with your own name and
email, then look at your sheet. A tab called **Users** appears with one row.

If no row appears, open the log at `%LOCALAPPDATA%\NaukriJobAutomation\logs\app.log` and look
for a line starting with `Registration was not sent`. The tool tries again each time it starts.

## Things to know

- **The link is public** once it is in your repository, so anyone could send made-up rows to
  it. The script only accepts a name, a valid-looking email and an install ID, limits their
  length, and stops any of them from running as a spreadsheet formula. It cannot tell a real
  user from a made-up one.
- **One row per copy of the tool.** If the same person runs setup again, their row is updated.
- **Changing the script later:** edit it, then **Deploy > Manage deployments > edit > New
  version**. The link stays the same. Making a *new deployment* gives a new link, which you
  would have to paste into `config.py` again.
- **To stop collecting:** set `OWNER_REGISTRATION_URL` back to `""`. The notice disappears
  from the welcome step and nothing is sent.
- You are responsible for the details you collect. Use them only for what the notice says,
  and delete a person's row if they ask.

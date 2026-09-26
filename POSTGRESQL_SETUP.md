# PostgreSQL Setup Guide for Skill Swap Project

## For Windows Users

### Step 1 Download and Install PostgreSQ
1. Visit: https://www.postgresql.org/download/windows/
2. Download PostgreSQL 15+ installer
3. Run the installer and follow the setup wizard
4. **Important:** Remember the password you set for the `postgres` user during installation
5. Keep the default port as `5432`

### Step 2: Start PostgreSQL Service
1. Press `Win + R` and type `services.msc`
2. Find "postgresql-x64-15" (or your version)
3. Right-click and select "Start"
4. Or use PowerShell as Administrator:
   ```powershell
   Start-Service postgresql-x64-15
   ```

### Step 3: Create the Database
Open PowerShell or Command Prompt and run:
```powershell
# Connect to PostgreSQL
psql -U postgres

# In the PostgreSQL prompt, create the database:
CREATE DATABASE skillswap_db;
\q
```

Or use pgAdmin (installed with PostgreSQL):
1. Open pgAdmin (search in Start menu)
2. Right-click "Databases" → Create → Database
3. Name: `skillswap_db`
4. Click "Save"

### Step 4: Update .env File
Edit the `.env` file in your project root:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=skillswap_db
DB_USER=postgres
DB_PASSWORD=postgres
```

Replace `your_postgres_password` with the password you set during PostgreSQL installation.

### Step 5: Run the Application
```powershell
python app.py
```

## Troubleshooting

### Error: "Connection refused"
- Make sure PostgreSQL service is running
- Check if port 5432 is not blocked by firewall
- Verify credentials in .env file

### Error: "Database skillswap_db does not exist"
- Run the CREATE DATABASE command above

### Error: "Password authentication failed"
- Check your password in the .env file
- Reset PostgreSQL password if forgotten

## Verify PostgreSQL Connection
```powershell
psql -U postgres -h localhost
```

You should see the PostgreSQL command prompt if connection is successful.

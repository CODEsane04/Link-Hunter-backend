const express = require('express');
const cors = require('cors');
const apiRoutes = require('./routes/api.js');
const dotenv = require('dotenv');

dotenv.config();
const app = express();

//middlewares
app.use(cors());
app.use(express.json());

//API routes
app.use('/api', apiRoutes);

//host the server
app.listen(process.env.PORT || 3000, () => {
    console.log(`Server is running on http://localhost:${process.env.PORT || 3000}`);
})

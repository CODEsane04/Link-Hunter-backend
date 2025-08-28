const express = require('express');
const { spawn } = require('child_process');
const router = express.Router();

//define the POST endpoint

router.post('/get-url', (req, res) => {
    // Get the image URL from the request body sent by the extension
    const { imageUrl } = req.body;

    if (!imageUrl) {
        return res.status(400).json({ error: 'No image URL provided' });
    }

    console.log("recieved image url : ", imageUrl);

    // Spawn a Python child process
    // The first argument is 'python' or 'python3'
    // The second is an array containing the script path and any arguments
    const pythonExecutablePath = '/usr/bin/python3';
    const Python_process = spawn(pythonExecutablePath, ['./python_scripts/find_links.py', imageUrl]);

    let result_data = '';
    let error_data = '';

    // Listen for data coming from the Python script's standard output
    //data arrives in chunks, that is why we keep adding the chunks to the result_data
    Python_process.stdout.on('data', (data) => {
        result_data += data.toString();
    });

    // Listen for any errors from the Python script
    Python_process.stderr.on('error', (error) => {
        error_data += error.toString();
    });

    //when the python script finishes, and all the data has been gathered,
    //we can then convert it into a JSON format
    Python_process.on('close', (code) => {
        if (code !== 0 || error_data) {
            console.log(`Python script error : ${error_data}`);
            return res.status(500).json({error : 'failed to process the image'});
        }

        try {
            console.log("image processed successfully by the python script");
            
            //parse the json script recieved from he python
            const results = JSON.parse(result_data);
            //send parse results back to extension
            console.log("sending the results back to the extension : ", results);
            res.json(results);

        } catch (e) {
            console.log("error parsing JSON from python script : ", e);
            return res.status(500).json({ error: 'Failed to parse results from script.' }); 
        }
    });
    
});

module.exports = router;
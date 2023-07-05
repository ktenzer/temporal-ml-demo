from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import pandas as pd
import asyncio
import uuid
import os
import pathlib
from typing import List, Dict
from temporalio.exceptions import FailureError
from temporalio.client import WorkflowFailureError
from client import get_client
from activities import UserSentimentInput, Signal
from workflow import ReviewProcessingWorkflow
app = Flask(__name__)

WORKFLOW_NAME = "reviews"
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/', methods=['GET'])
async def index():
    return render_template('index.html')

@app.route('/locations', methods=['POST'])
async def locations():
    file = request.files['file']
    labels = request.form.getlist('labels')

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Start booking workflow
        client = await get_client()

        id = str(uuid.uuid4().int)[:6]

        input = UserSentimentInput(
            filepath = filepath,
        ) 
    
        workflow = await client.start_workflow(
            ReviewProcessingWorkflow.run,
            input,
            id=f'{WORKFLOW_NAME}-{id}',
            task_queue="activity_sticky_queue-distribution-queue",
        )

        locations = []
        while not locations:
            try:
                locations = await workflow.query(ReviewProcessingWorkflow.locations)        
            except:
                pass

        path = pathlib.PurePath(filepath)
        file=path.name
        return render_template('locations.html', locations=locations, id=id, file=file, labels=labels)                
    else:
        return "No file selected." 
@app.route('/upload/<id>/<file>/<path:labels>', methods=['POST'])
async def upload(id, file, labels):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
    labels = labels.split('/')

    client = await get_client()

    input = Signal(
        filepath = filepath,
        location = request.form.get('location'),
        labels = labels
    ) 

    workflow = client.get_workflow_handle(f'{WORKFLOW_NAME}-{id}')

    await workflow.signal(ReviewProcessingWorkflow.pending_user_sentiment, input)

    result = []
    while not result:
        try:
            result = await workflow.query(ReviewProcessingWorkflow.results)        
        except:
            pass

    filtered_df = pd.DataFrame()
    filtered_df = filtered_df.assign(Text=None)
    filtered_df = filtered_df.assign(Sentiment=None)
    filtered_df = filtered_df.assign(Probability=None)

    i = 0            
    for item in result.text:  
        filtered_df.loc[result.index[i]] = [item, result.sentiment[i], result.probability[i]]
        i += 1

    return render_template('table.html', table=filtered_df.to_html(index=True), location=request.form.get('location')) 

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)    
